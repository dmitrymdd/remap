r"""Готовит логотип шапки из art/logo.png: src/remap/assets/logo@{1,2,3}x.png, logo_hover@Nx.png и logo_glow@Nx.png.

Запуск (из корня репозитория): .venv\Scripts\python tools\build_logo.py
Pillow нужен только здесь (requirements-dev.txt), приложение читает готовые PNG.

- logo — логотип без прозрачных полей, вписан в слот 144×22 (Lanczos) по центру;
- logo_hover — то же, яркость × 1.15 (`brightness(1.15)` у `.logo-btn:hover` в макете);
- logo_glow — `drop-shadow(0 0 5px rgba(255,255,255,.45))`: альфа логотипа, размытая гауссом σ = blur / 2, белая,
  45 %; холст шире слота на GLOW_PAD с каждой стороны (тень выходит за слот).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from remap.ui import theme

SOURCE = ROOT / "art" / "logo.png"
OUT = ROOT / "src" / "remap" / "assets"
SCALES = (1, 2, 3)
CROP_ALPHA = 8  # прозрачнее — поле (у исходника вокруг букв едва заметная дымка)


def cropped(src: Image.Image) -> Image.Image:
    alpha = src.getchannel("A").point(lambda v: 255 if v > CROP_ALPHA else 0)
    return src.crop(alpha.getbbox())


def fitted(logo: Image.Image, scale: int) -> Image.Image:
    """Логотип в слоте LOGO_SIZE × scale: по меньшему из отношений сторон, по центру."""
    slot_w, slot_h = (v * scale for v in theme.LOGO_SIZE)
    k = min(slot_w / logo.width, slot_h / logo.height)
    w, h = round(logo.width * k), round(logo.height * k)
    canvas = Image.new("RGBA", (slot_w, slot_h), (0, 0, 0, 0))
    canvas.alpha_composite(logo.resize((w, h), Image.Resampling.LANCZOS), ((slot_w - w) // 2, (slot_h - h) // 2))
    return canvas


def brightened(img: Image.Image, factor: float) -> Image.Image:
    r, g, b, a = img.split()
    r, g, b = (c.point(lambda v: min(255, round(v * factor))) for c in (r, g, b))
    return Image.merge("RGBA", (r, g, b, a))


def glow(img: Image.Image, scale: int) -> Image.Image:
    pad, spec = theme.LOGO_GLOW_PAD * scale, theme.LOGO_GLOW
    alpha = Image.new("L", (img.width + 2 * pad, img.height + 2 * pad), 0)
    alpha.paste(img.getchannel("A"), (pad, pad))
    alpha = alpha.filter(ImageFilter.GaussianBlur(spec["blur"] / 2 * scale))
    alpha = alpha.point(lambda v: round(v * spec["alpha"]))
    out = Image.new("RGBA", alpha.size, (*spec["rgb"], 0))
    out.putalpha(alpha)
    return out


def main() -> None:
    logo = cropped(Image.open(SOURCE).convert("RGBA"))
    for n in SCALES:
        img = fitted(logo, n)
        img.save(OUT / f"logo@{n}x.png", optimize=True)
        brightened(img, theme.LOGO_HOVER_BRIGHTNESS).save(OUT / f"logo_hover@{n}x.png", optimize=True)
        glow(img, n).save(OUT / f"logo_glow@{n}x.png", optimize=True)
        print(f"logo@{n}x: {img.width}x{img.height}")


if __name__ == "__main__":
    main()
