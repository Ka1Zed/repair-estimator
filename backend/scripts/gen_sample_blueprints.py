"""Генератор синтетических планов помещений для отладки распознавания.

Лицензионно чистые фикстуры: рисуем контур комнаты, размерные линии с подписями
в мм, дверь и окно. Подписи в мм — проверяем, что модель читает их и масштаб
считается сам (4000мм → 4.0м).

Запуск из backend/:  python scripts/gen_sample_blueprints.py
Кладёт PNG в scripts/sample_blueprints/.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "sample_blueprints"
WALL = (30, 30, 30)
DIM = (110, 110, 110)
BG = (255, 255, 255)


def _font(size: int):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _dim_label(d: ImageDraw.ImageDraw, x: float, y: float, text: str, f):
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.rectangle((x - tw / 2 - 3, y - th / 2 - 2, x + tw / 2 + 3, y + th / 2 + 2), fill=BG)
    d.text((x - tw / 2, y - th / 2), text, fill=DIM, font=f)


def rect_room():
    """Прямоугольник 4000x3000 мм с дверью и окном."""
    img = Image.new("RGB", (900, 700), BG)
    d = ImageDraw.Draw(img)
    f = _font(22)
    x0, y0, x1, y1 = 150, 120, 750, 570  # 600x450 px ~ 4000x3000 мм
    d.rectangle((x0, y0, x1, y1), outline=WALL, width=6)
    # дверь снизу
    d.line((x0 + 220, y1, x0 + 320, y1), fill=BG, width=8)
    d.arc((x0 + 220, y1 - 100, x0 + 420, y1 + 100), 180, 270, fill=WALL, width=2)
    # окно справа
    d.line((x1, y0 + 150, x1, y0 + 280), fill=(80, 80, 200), width=8)
    # размеры
    _dim_label(d, (x0 + x1) / 2, y0 - 40, "4000", f)
    _dim_label(d, x1 + 50, (y0 + y1) / 2, "3000", f)
    _dim_label(d, x0 + 270, y1 + 45, "дверь 900", _font(16))
    _dim_label(d, x1 + 55, y0 + 215, "окно 1300", _font(16))
    d.text((x0 + 20, y0 + 20), "Гостиная  h=2700", fill=WALL, font=f)
    return img


def l_room():
    """L-образная комната с подписями сторон в мм."""
    img = Image.new("RGB", (900, 800), BG)
    d = ImageDraw.Draw(img)
    f = _font(20)
    # вершины по часовой (px)
    pts = [(150, 150), (700, 150), (700, 450), (450, 450), (450, 650), (150, 650)]
    d.line(pts + [pts[0]], fill=WALL, width=6, joint="curve")
    labels = ["5000", "2500", "2000", "1500", "3000", "4000"]
    for i, lab in enumerate(labels):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        off = (0, -28) if abs(a[1] - b[1]) < 5 else (40, 0)
        _dim_label(d, mx + off[0], my + off[1], lab, f)
    d.text((180, 180), "Кухня  h=2650", fill=WALL, font=f)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("rect_room.png", rect_room), ("l_room.png", l_room)):
        path = OUT / name
        fn().save(path)
        print(f"saved {path}")


if __name__ == "__main__":
    main()
