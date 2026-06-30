import os
import io
import json
import re
import logging
import statistics
from typing import Dict, Any, Optional, List
from PIL import Image

logger = logging.getLogger(__name__)

# Разрешение, до которого ужимаем картинку перед отправкой в модель.
# 2048 (вместо прежних 1024) — чтобы оставались читаемыми подписи размеров на стенах.
DEFAULT_MAX_SIDE = int(os.getenv("BLUEPRINT_MAX_SIDE", "2048"))

# Стратегия промпта: модель возвращает ТОЛЬКО пиксельные углы контура и реально
# прочитанные размеры рёбер. Масштаб (м/px), метры и нормализованные координаты
# для оверлея мы считаем сами на бэке — это надёжнее, чем просить модель
# одновременно «видеть» пиксели и считать метры.
def _vision_prompt(width: int, height: int) -> str:
    return f"""Ты анализируешь архитектурный план ОДНОГО помещения (комнаты).
Размер изображения — {width}x{height} пикселей, начало координат (0,0) — левый верхний угол,
ось X вправо, ось Y вниз.

Верни структурированный JSON строго по заданной схеме. Без markdown, без пояснений.

Поля:
- corners_px: углы внутреннего контура стен комнаты по порядку обхода ПО ЧАСОВОЙ стрелке,
  каждый угол — объект {{"x": <px>, "y": <px>}} в пикселях относительно изображения
  {width}x{height}. Минимум 3, обычно 4.
- edge_dimensions: размеры, которые ты ТОЧНО прочитал на чертеже, привязанные к рёбрам.
  Ребро соединяет corners_px[from_index] и corners_px[to_index] (это соседние углы).
  length_m — длина ребра в МЕТРАХ (переведи: 3200мм → 3.2; 320см → 3.2; «3,2 м» → 3.2).
  Добавляй ТОЛЬКО реально прочитанные числа. Не уверен — не добавляй ребро.
- ceiling_height_m: высота потолка в метрах, если указана; иначе 0.
- openings: двери (door) и окна (window) с width_m и height_m в метрах, если читаются.
- raw_dimensions: все размерные надписи с чертежа как строки — для контроля.
- notes: короткие замечания, если что-то неоднозначно.

Важно: corners_px должны точно лежать на углах комнаты — по ним строится оверлей.
Размеры не выдумывай: лучше пустой edge_dimensions, чем неверный масштаб."""


# Схема для structured output Gemini (response_schema). Описана через protos.Schema,
# чтобы не зависеть от поддержки TypedDict в конкретной версии SDK.
def _gemini_schema():
    from google.generativeai import protos

    T = protos.Type
    point = protos.Schema(
        type=T.OBJECT,
        properties={"x": protos.Schema(type=T.NUMBER), "y": protos.Schema(type=T.NUMBER)},
        required=["x", "y"],
    )
    edge = protos.Schema(
        type=T.OBJECT,
        properties={
            "from_index": protos.Schema(type=T.INTEGER),
            "to_index": protos.Schema(type=T.INTEGER),
            "length_m": protos.Schema(type=T.NUMBER),
        },
        required=["from_index", "to_index", "length_m"],
    )
    opening = protos.Schema(
        type=T.OBJECT,
        properties={
            "type": protos.Schema(type=T.STRING),
            "width_m": protos.Schema(type=T.NUMBER),
            "height_m": protos.Schema(type=T.NUMBER),
        },
        required=["type", "width_m", "height_m"],
    )
    return protos.Schema(
        type=T.OBJECT,
        properties={
            "corners_px": protos.Schema(type=T.ARRAY, items=point),
            "edge_dimensions": protos.Schema(type=T.ARRAY, items=edge),
            "ceiling_height_m": protos.Schema(type=T.NUMBER),
            "openings": protos.Schema(type=T.ARRAY, items=opening),
            "raw_dimensions": protos.Schema(type=T.ARRAY, items=protos.Schema(type=T.STRING)),
            "notes": protos.Schema(type=T.ARRAY, items=protos.Schema(type=T.STRING)),
        },
        required=["corners_px"],
    )


class BlueprintService:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # gemini-2.5-flash по умолчанию: gemini-2.5-pro недоступен на бесплатном
        # тарифе (free-tier quota = 0), нужен платный проект. Переопределяется env.
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        # Модель Claude (основной путь распознавания). Дефолт — claude-sonnet-5
        # (vision + дёшево для агентных задач); claude-haiku-4-5 дешевле,
        # claude-opus-4-8 точнее и дороже.
        self.claude_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    def process_blueprint(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        logger.debug(f"START process_blueprint: {filename}")

        if os.getenv("BLUEPRINT_MOCK", "").lower() == "true":
            logger.debug("MOCK mode")
            return self._mock_response()

        try:
            image = self._prepare_image(file_bytes, filename)
            logger.debug(f"image ready: {image.size}")
        except NotImplementedError as e:
            return self._error_response(str(e))
        except Exception as e:
            logger.warning(f"image error: {e}")
            return self._error_response(f"Ошибка обработки файла: {str(e)}")

        methods = self._method_priority()
        logger.debug(f"methods: {methods}")

        if not methods:
            return self._error_response("Нет доступного метода распознавания. Проверь .env и доступность Ollama/API.")

        last_error = None
        for method in methods:
            try:
                if method == "gemini":
                    return self._process_with_gemini(image)
                if method == "claude":
                    return self._process_with_claude(image)
                if method == "ollama":
                    return self._process_with_ollama(image)
            except Exception as e:
                # Claude не проходит pre-flight проверку (в отличие от Gemini/Ollama) —
                # битый ключ/нет кредита/нет сети вылезает только на реальном вызове.
                # Откатываемся на следующий метод вместо немедленной ошибки.
                logger.warning(f"{method} error: {e}, пробую следующий метод")
                last_error = e

        return self._error_response(f"Все методы распознавания недоступны. Последняя ошибка: {last_error}")

    def _prepare_image(self, file_bytes: bytes, filename: str) -> Image.Image:
        if filename.lower().endswith(".pdf"):
            try:
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_bytes, first_page=1, last_page=1, dpi=200)
                return pages[0].convert("RGB")
            except ImportError:
                raise NotImplementedError("pdf2image не установлен. Используйте PNG или JPG.")
            except Exception as e:
                raise RuntimeError(f"Ошибка конвертации PDF: {e}")
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")

    def _choose_method(self) -> str:
        """Метод, который будет использован первым (см. _method_priority)."""
        methods = self._method_priority()
        return methods[0] if methods else "none"

    def _method_priority(self) -> List[str]:
        # Claude — основной путь; Gemini понижен до fallback (датацентровые/
        # региональные 403 и квоты free-tier). Локалка (Ollama/CubiCasa) — по roadmap.
        # Возвращаем именно цепочку приоритетов: process_blueprint пробует методы по
        # порядку и откатывается на следующий, если вызов реально упал (например,
        # ANTHROPIC_API_KEY задан, но невалиден/нет кредита — это не ловится здесь,
        # только на вызове API).
        methods = []
        if self.anthropic_key:
            methods.append("claude")
        gemini_enabled = os.getenv("GEMINI_ENABLED", "true").lower() != "false"
        if gemini_enabled and self.gemini_key and self._is_gemini_reachable():
            methods.append("gemini")
        if self._is_ollama_available():
            methods.append("ollama")
        return methods

    def _is_gemini_reachable(self) -> bool:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.gemini_key}"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                return True
            logger.warning(f"Gemini API вернул {resp.status_code}, переключаюсь на Ollama")
            return False
        except Exception:
            logger.warning("Gemini API недоступен (сеть/регион), переключаюсь на Ollama")
            return False

    def _mock_response(self) -> Dict[str, Any]:
        return {
            "success": True,
            "method": "gemini",
            "confidence": 0.85,
            "points": [
                {"x": 0.0, "y": 0.0, "nx": 0.1, "ny": 0.1},
                {"x": 4.5, "y": 0.0, "nx": 0.9, "ny": 0.1},
                {"x": 4.5, "y": 3.2, "nx": 0.9, "ny": 0.9},
                {"x": 0.0, "y": 3.2, "nx": 0.1, "ny": 0.9},
            ],
            "height": 2.7,
            "openings": [
                {"type": "door", "width": 0.9, "height": 2.0},
                {"type": "window", "width": 1.4, "height": 1.2},
            ],
            "raw_dimensions": ["4.5м", "3.2м", "2.7м"],
            "warnings": ["MOCK-режим: реальное распознавание отключено (BLUEPRINT_MOCK=true)"],
        }

    def _resize_image(self, image: Image.Image, max_side: int = DEFAULT_MAX_SIDE) -> Image.Image:
        w, h = image.size
        if max(w, h) <= max_side:
            return image
        scale = max_side / max(w, h)
        return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    def _is_ollama_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=3)
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            has_llava = any("llava" in m for m in models)
            if not has_llava:
                logger.warning(f"Ollama запущен, но llava не найдена. Модели: {models}")
            return has_llava
        except Exception as e:
            logger.warning(f"Ollama недоступен: {e}")
            return False

    def _process_with_gemini(self, image: Image.Image) -> Dict[str, Any]:
        import google.generativeai as genai
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        logger.debug(f"configuring Gemini ({self.gemini_model})...")
        # transport="rest": gRPC-транспорт (дефолт SDK) в ряде регионов виснет до таймаута,
        # хотя обычный HTTPS работает. Принудительно используем REST.
        genai.configure(api_key=self.gemini_key, transport="rest")

        image = self._resize_image(image)
        w, h = image.size
        logger.debug(f"image resized to {image.size}")

        model = genai.GenerativeModel(
            self.gemini_model,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": _gemini_schema(),
                "temperature": 0.0,
            },
        )

        timeout = int(os.getenv("BLUEPRINT_TIMEOUT", "90"))
        parts = [_vision_prompt(w, h), image]

        def _call():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(model.generate_content, parts)
                try:
                    return future.result(timeout=timeout)
                except FuturesTimeout:
                    logger.warning("Gemini timeout!")
                    raise RuntimeError(f"Gemini API не ответил за {timeout} секунд. Проверь соединение.")

        logger.debug(f"calling generate_content (timeout={timeout}s)...")
        try:
            response = _call()
        except Exception as e:
            # 429 free-tier: сервер подсказывает retryDelay — один аккуратный ретрай.
            delay = self._retry_delay_on_429(e)
            if delay is None:
                raise
            import time
            logger.warning(f"Gemini 429, ждём {delay}s и пробуем ещё раз...")
            time.sleep(min(delay, 40))
            response = _call()

        logger.debug(f"Gemini response: {response.text[:300]}")
        data = self._extract_json(response.text)
        result = self._normalize_extract(data, img_size=image.size)
        result["method"] = "gemini"
        return result

    def _retry_delay_on_429(self, exc: Exception) -> Optional[float]:
        """Возвращает паузу из retryDelay для 429, либо None если ретрай не поможет."""
        msg = str(exc)
        if "429" not in msg:
            return None
        # limit: 0 — модель недоступна на текущем тарифе (напр. gemini-2.5-pro на free).
        # Ретрай бесполезен, отдаём понятное сообщение.
        if "limit: 0" in msg:
            raise RuntimeError(
                f"Модель {self.gemini_model} недоступна на бесплатном тарифе Gemini "
                f"(квота 0). Используй GEMINI_MODEL=gemini-2.5-flash или подключи биллинг."
            )
        # Дневная квота (PerDay) — пауза в секундах её не вернёт. Ретрай только сожжёт
        # ещё один запрос и время. Падаем сразу с понятным сообщением.
        if "PerDay" in msg or "RequestsPerDay" in msg:
            raise RuntimeError(
                f"Исчерпан дневной лимит бесплатного тарифа Gemini для {self.gemini_model} "
                f"(20 запросов/сутки). Подожди сброса квоты (полночь по тихоокеанскому времени) "
                f"или подключи биллинг. Пока можно калибровать чертёж вручную."
            )
        m = re.search(r"retry in ([\d.]+)s|retryDelay['\"]?:\s*['\"]?(\d+)", msg)
        if m:
            return float(m.group(1) or m.group(2))
        return 15.0

    def _process_with_claude(self, image: Image.Image) -> Dict[str, Any]:
        import base64
        import anthropic

        image = self._resize_image(image)
        w, h = image.size
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        logger.debug(f"calling Claude API ({self.claude_model})...")
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=self.claude_model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": _vision_prompt(w, h)},
                    ],
                }
            ],
        )
        # Берём первый текстовый блок (а не content[0]): модель может вернуть
        # сначала thinking-блок и т.п.
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        logger.debug(f"Claude response: {text[:300]}")
        data = self._extract_json(text)
        result = self._normalize_extract(data, img_size=image.size)
        result["method"] = "claude"
        return result

    def _process_with_ollama(self, image: Image.Image) -> Dict[str, Any]:
        import base64
        import requests

        image = self._resize_image(image)
        w, h = image.size
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = {
            "model": "llava",
            "prompt": _vision_prompt(w, h),
            "images": [b64],
            "stream": False,
            "format": "json",
        }
        logger.debug(f"calling Ollama llava (timeout=180s, image size {len(b64)//1024}KB base64)...")
        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=180)
        resp.raise_for_status()
        text = resp.json().get("response", "")
        logger.debug(f"Ollama response: {text[:200]}")
        data = self._extract_json(text)
        result = self._normalize_extract(data, img_size=image.size)
        result["method"] = "ollama"
        return result

    # ---- разбор и нормализация ----

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Достаёт JSON-объект из ответа модели (structured output или свободный текст)."""
        clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}

    def _normalize_extract(self, data: Dict[str, Any], img_size: tuple) -> Dict[str, Any]:
        """Превращает сырой extract модели в контракт BlueprintUploadResponse.

        Масштаб (м/px) считаем сами из edge_dimensions, метры и nx/ny — тоже сами.
        """
        if not isinstance(data, dict):
            return self._error_response("Модель не вернула JSON. Попробуйте другой чертеж.")

        img_w, img_h = (img_size[0] or 1), (img_size[1] or 1)
        warnings: List[str] = []

        corners_px = self._validate_px_points(data.get("corners_px", []))
        if len(corners_px) < 3:
            warnings.append("Не удалось извлечь контур помещения — нужно как минимум 3 точки.")

        height = self._validate_height(data.get("ceiling_height_m"))
        openings = self._validate_openings(data.get("openings", []))
        raw_dimensions = [str(d) for d in data.get("raw_dimensions", []) if isinstance(d, (str, int, float))]
        for n in data.get("notes", []) if isinstance(data.get("notes"), list) else []:
            if isinstance(n, str) and n.strip():
                warnings.append(n.strip())

        # Масштаб из прочитанных размеров рёбер: медиана length_m / px_len.
        m_per_px = self._scale_from_edges(data.get("edge_dimensions", []), corners_px)
        if m_per_px is None and len(corners_px) >= 3:
            warnings.append("Масштаб не определён по размерам — откалибруй вручную.")

        # Точки контракта: nx/ny (для оверлея) из пикселей, x/y (метры) из масштаба.
        points: List[Dict[str, Any]] = []
        origin = corners_px[0] if corners_px else {"x": 0, "y": 0}
        for p in corners_px:
            point = {
                "x": round((p["x"] - origin["x"]) * m_per_px, 2) if m_per_px else 0.0,
                "y": round((p["y"] - origin["y"]) * m_per_px, 2) if m_per_px else 0.0,
                "nx": round(p["x"] / img_w, 4),
                "ny": round(p["y"] / img_h, 4),
            }
            points.append(point)

        confidence = self._calc_confidence(points, height, openings, warnings, scale_found=m_per_px is not None)

        return {
            "success": len(points) >= 3,
            "method": "none",  # перезапишет вызывающий код
            "confidence": confidence,
            "points": points,
            "height": height,
            "openings": openings,
            "raw_dimensions": raw_dimensions,
            "warnings": warnings,
        }

    def _validate_px_points(self, raw: Any) -> List[Dict[str, float]]:
        if not isinstance(raw, list):
            return []
        result = []
        for p in raw:
            # Vision-модель без JSON-схемы (Claude/Ollama) возвращает угол то как
            # {"x":..,"y":..}, то как [x, y] — принимаем оба, иначе контур теряется.
            if isinstance(p, dict) and "x" in p and "y" in p:
                x, y = p["x"], p["y"]
            elif isinstance(p, (list, tuple)) and len(p) == 2:
                x, y = p[0], p[1]
            else:
                continue
            try:
                result.append({"x": float(x), "y": float(y)})
            except (TypeError, ValueError):
                pass
        return result

    def _scale_from_edges(self, raw: Any, corners_px: List[Dict[str, float]]) -> Optional[float]:
        """м/px как медиана отношений length_m / пиксельная_длина_ребра."""
        if not isinstance(raw, list) or len(corners_px) < 2:
            return None
        n = len(corners_px)
        ratios = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            try:
                i = int(e["from_index"])
                j = int(e["to_index"])
                length_m = float(e["length_m"])
            except (TypeError, ValueError, KeyError):
                continue
            if not (0 <= i < n and 0 <= j < n) or i == j or length_m <= 0:
                continue
            a, b = corners_px[i], corners_px[j]
            px = ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5
            if px > 0:
                ratios.append(length_m / px)
        if not ratios:
            return None
        return statistics.median(ratios)

    def _validate_openings(self, raw: Any) -> list:
        if not isinstance(raw, list):
            return []
        result = []
        for o in raw:
            if not isinstance(o, dict):
                continue
            t = o.get("type")
            if t not in ("door", "window"):
                continue
            try:
                width = float(o.get("width_m", o.get("width")))
                hgt = float(o.get("height_m", o.get("height")))
                result.append({"type": t, "width": width, "height": hgt})
            except (TypeError, ValueError):
                pass
        return result

    def _validate_height(self, raw: Any) -> Optional[float]:
        if raw is None:
            return None
        try:
            h = float(raw)
            return h if 1.5 <= h <= 6.0 else None
        except (TypeError, ValueError):
            return None

    def _calc_confidence(self, points: list, height: Optional[float], openings: list,
                         warnings: list, scale_found: bool = False) -> float:
        score = 0.0
        if len(points) >= 4:
            score += 0.4
        elif len(points) == 3:
            score += 0.25
        if scale_found:
            score += 0.25
        if height is not None:
            score += 0.2
        if openings:
            score += 0.1
        penalty = min(len(warnings) * 0.05, 0.2)
        return round(max(0.0, min(1.0, score - penalty)), 2)

    def _error_response(self, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "method": "none",
            "confidence": 0.0,
            "points": [],
            "height": None,
            "openings": [],
            "raw_dimensions": [],
            "warnings": [message],
        }
