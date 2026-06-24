"""Eval beta-распознавания чертежей: прогон BlueprintService на картинках.

Что делает:
  - гоняет реальный пайплайн (Gemini/Claude/Ollama по .env) на каждом файле;
  - печатает извлечённые точки/масштаб/проёмы/предупреждения;
  - рисует оверлей-полигон поверх чертежа в scripts/eval_out/<имя>_overlay.png,
    чтобы глазами проверить, садятся ли углы на контур.

Нужен ключ в корневом .env (GEMINI_API_KEY) — без него метод будет "none".
Модель переопределяется через GEMINI_MODEL (по умолчанию gemini-2.5-pro).
Сравнить pro и flash:
    GEMINI_MODEL=gemini-2.5-pro  python scripts/eval_blueprint.py
    GEMINI_MODEL=gemini-2.5-flash python scripts/eval_blueprint.py

Запуск из backend/:
    python scripts/eval_blueprint.py                      # по sample_blueprints/
    python scripts/eval_blueprint.py path/to/plan.png ... # свои файлы
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ на путь
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.services.blueprint_service import BlueprintService  # noqa: E402

SAMPLES = Path(__file__).parent / "sample_blueprints"
OUT = Path(__file__).parent / "eval_out"


def draw_overlay(src: Path, result: dict) -> Path | None:
    pts = result.get("points", [])
    if not pts or not all(p.get("nx") is not None for p in pts):
        return None
    img = Image.open(src).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    poly = [(p["nx"] * w, p["ny"] * h) for p in pts]
    d.polygon(poly, fill=(176, 123, 94, 60), outline=(176, 70, 40, 255), width=4)
    for i, (x, y) in enumerate(poly):
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(255, 255, 255, 255), outline=(176, 70, 40, 255), width=3)
        d.text((x + 9, y - 9), str(i), fill=(176, 70, 40, 255))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{src.stem}_overlay.png"
    img.save(out)
    return out


def fmt_scale(result: dict) -> str:
    pts = result.get("points", [])
    if len(pts) >= 2 and any(p["x"] or p["y"] for p in pts):
        xs = [p["x"] for p in pts]
        ys = [p["y"] for p in pts]
        return f"bbox ≈ {max(xs) - min(xs):.2f} x {max(ys) - min(ys):.2f} м"
    return "масштаб не определён (ручная калибровка)"


def main():
    args = sys.argv[1:]
    files = [Path(a) for a in args] if args else sorted(SAMPLES.glob("*.png")) + sorted(SAMPLES.glob("*.jpg"))
    if not files:
        print("Нет файлов. Сгенерируй: python scripts/gen_sample_blueprints.py")
        return

    svc = BlueprintService()
    print(f"Доступный метод: {svc._choose_method()}  | модель Gemini: {svc.gemini_model}\n")

    for f in files:
        if not f.exists():
            print(f"!! нет файла: {f}")
            continue
        print(f"=== {f.name} ===")
        result = svc.process_blueprint(f.read_bytes(), f.name)
        print(f"  method={result['method']} success={result['success']} confidence={result['confidence']}")
        print(f"  углов: {len(result['points'])} | высота: {result['height']} | {fmt_scale(result)}")
        if result["openings"]:
            print(f"  проёмы: {result['openings']}")
        if result["raw_dimensions"]:
            print(f"  размеры: {result['raw_dimensions']}")
        for w in result["warnings"]:
            print(f"  ⚠ {w}")
        overlay = draw_overlay(f, result)
        if overlay:
            print(f"  оверлей: {overlay}")
        print()


if __name__ == "__main__":
    main()
