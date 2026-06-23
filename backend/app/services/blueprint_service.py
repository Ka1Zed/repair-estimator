import os
import io
import json
import re
import logging
from typing import Dict, Any, Optional
from PIL import Image

logger = logging.getLogger(__name__)

VISION_PROMPT = """Проанализируй этот архитектурный чертеж помещения.

Верни ТОЛЬКО JSON без markdown-блоков и пояснений:
{
  "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
  "points_px": [{"x": 120, "y": 45}, {"x": 890, "y": 45}, {"x": 890, "y": 660}, {"x": 120, "y": 660}],
  "height": 2.7,
  "openings": [
    {"type": "door", "width": 0.8, "height": 2.0},
    {"type": "window", "width": 1.5, "height": 1.4}
  ],
  "raw_dimensions": ["4.0м", "3.0м"],
  "warnings": []
}

Правила:
- points: координаты углов помещения в метрах, начни с (0, 0), обходи по часовой стрелке
- points_px: те же углы, но в пикселях относительно изображения (для наложения на чертёж)
- height: высота потолка в метрах (null если не указана)
- openings: все двери и окна с размерами
- raw_dimensions: все размеры с чертежа как строки
- warnings: предупреждения если что-то неясно или отсутствует

Если масштаб не указан явно — оцени по стандартам (жилая комната 3–6м).
Верни ТОЛЬКО JSON."""


class BlueprintService:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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

        method = self._choose_method()
        logger.debug(f"method: {method}")

        try:
            if method == "gemini":
                return self._process_with_gemini(image)
            if method == "claude":
                return self._process_with_claude(image)
            if method == "ollama":
                return self._process_with_ollama(image)
        except Exception as e:
            logger.warning(f"{method} error: {e}")
            return self._error_response(f"Ошибка {method}: {str(e)}")

        return self._error_response("Нет доступного метода распознавания. Проверь .env и доступность Ollama/API.")

    def _prepare_image(self, file_bytes: bytes, filename: str) -> Image.Image:
        if filename.lower().endswith(".pdf"):
            try:
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_bytes, first_page=1, last_page=1, dpi=150)
                return pages[0]
            except ImportError:
                raise NotImplementedError("pdf2image не установлен. Используйте PNG или JPG.")
            except Exception as e:
                raise RuntimeError(f"Ошибка конвертации PDF: {e}")
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")

    def _choose_method(self) -> str:
        gemini_enabled = os.getenv("GEMINI_ENABLED", "true").lower() != "false"
        if gemini_enabled and self.gemini_key and self._is_gemini_reachable():
            return "gemini"
        if self.anthropic_key:
            return "claude"
        if self._is_ollama_available():
            return "ollama"
        return "none"

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

    def _resize_image(self, image: Image.Image, max_side: int = 1024) -> Image.Image:
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

        logger.debug("configuring Gemini...")
        genai.configure(api_key=self.gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Уменьшаем до 1024px по длинной стороне — меньше токенов, быстрее
        image = self._resize_image(image, max_side=1024)
        logger.debug(f"image resized to {image.size}")

        logger.debug("calling generate_content (timeout=60s)...")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, [VISION_PROMPT, image])
            try:
                response = future.result(timeout=60)
            except FuturesTimeout:
                logger.warning("Gemini timeout!")
                raise RuntimeError("Gemini API не ответил за 60 секунд. Проверь соединение.")

        logger.debug(f"Gemini response: {response.text[:300]}")
        result = self._parse_vision_json(response.text, img_size=image.size)
        result["method"] = "gemini"
        return result

    def _process_with_claude(self, image: Image.Image) -> Dict[str, Any]:
        import base64
        import anthropic

        image = self._resize_image(image, max_side=1024)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        logger.debug("calling Claude API (claude-opus-4-8)...")
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
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
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
        )
        text = response.content[0].text
        logger.debug(f"Claude response: {text[:300]}")
        result = self._parse_vision_json(text, img_size=image.size)
        result["method"] = "claude"
        return result

    def _process_with_ollama(self, image: Image.Image) -> Dict[str, Any]:
        import base64
        import requests

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = {
            "model": "llava",
            "prompt": VISION_PROMPT,
            "images": [b64],
            "stream": False,
        }
        logger.debug(f"calling Ollama llava (timeout=180s, image size {len(b64)//1024}KB base64)...")
        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=180)
        resp.raise_for_status()
        text = resp.json().get("response", "")
        logger.debug(f"Ollama response: {text[:200]}")
        result = self._parse_vision_json(text, img_size=image.size)
        result["method"] = "ollama"
        return result

    def _parse_vision_json(self, text: str, img_size: Optional[tuple] = None) -> Dict[str, Any]:
        """Извлекает JSON из ответа модели и нормализует структуру."""
        # Убираем возможные markdown-блоки
        clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        # Ищем первый {...}
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return self._error_response("Модель не вернула JSON. Попробуйте другой чертеж.")

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            return self._error_response(f"Ошибка парсинга JSON: {e}")

        points = self._validate_points(data.get("points", []))
        openings = self._validate_openings(data.get("openings", []))
        height = self._validate_height(data.get("height"))
        raw_warnings = data.get("warnings", [])
        warnings = []
        for w in raw_warnings if isinstance(raw_warnings, list) else []:
            if isinstance(w, str):
                warnings.append(w)
            elif isinstance(w, dict):
                warnings.append(w.get("warning") or w.get("message") or str(w))

        confidence = self._calc_confidence(points, height, openings, warnings)

        if len(points) < 3:
            warnings.append("Не удалось извлечь контур помещения — нужно как минимум 3 точки.")

        # Нормализованные координаты углов на изображении (0..1) — для оверлея полигона
        # поверх чертежа на фронте. Считаем из пиксельных координат модели.
        if img_size and img_size[0] > 0 and img_size[1] > 0:
            points_px = data.get("points_px", [])
            for i, p in enumerate(points):
                if i < len(points_px) and isinstance(points_px[i], dict):
                    try:
                        p["nx"] = round(float(points_px[i]["x"]) / img_size[0], 4)
                        p["ny"] = round(float(points_px[i]["y"]) / img_size[1], 4)
                    except (TypeError, ValueError, KeyError):
                        pass

        return {
            "success": len(points) >= 3,
            "method": "none",  # будет перезаписан вызывающим кодом
            "confidence": confidence,
            "points": points,
            "height": height,
            "openings": openings,
            "raw_dimensions": data.get("raw_dimensions", []),
            "warnings": warnings,
        }

    def _validate_points(self, raw: Any) -> list:
        if not isinstance(raw, list):
            return []
        result = []
        for p in raw:
            if isinstance(p, dict) and "x" in p and "y" in p:
                try:
                    result.append({"x": float(p["x"]), "y": float(p["y"])})
                except (TypeError, ValueError):
                    pass
        return result

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
                item = {"type": t, "width": float(o["width"]), "height": float(o["height"])}
                if "position" in o and isinstance(o["position"], dict):
                    pos = o["position"]
                    item["position"] = {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))}
                result.append(item)
            except (TypeError, ValueError, KeyError):
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

    def _calc_confidence(self, points: list, height: Optional[float], openings: list, warnings: list) -> float:
        score = 0.0
        if len(points) >= 4:
            score += 0.5
        elif len(points) == 3:
            score += 0.3
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
