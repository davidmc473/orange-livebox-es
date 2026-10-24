"""Genera los iconos de la integración (diseño original, sin logotipos de terceros).

Uso: ``python scripts/make_brand.py`` (requiere Pillow). Escribe en
``custom_components/orange_livebox_es/brand/`` los ficheros que Home Assistant sirve para
integraciones personalizadas: ``icon.png`` (256 px), ``icon@2x.png`` (512 px) y sus
variantes ``dark_`` para el tema oscuro.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "custom_components" / "orange_livebox_es" / "brand"
SS = 4  # supermuestreo para bordes suaves
BASE = 512  # lienzo lógico

ORANGE = (255, 121, 0, 255)
ORANGE_DARK = (214, 92, 0, 255)
WHITE = (255, 255, 255, 255)


def _draw(arc_color: tuple[int, int, int, int]) -> Image.Image:
    size = BASE * SS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def s(v: float) -> int:
        return round(v * SS)

    # Señal WiFi: tres arcos y un punto, centrados sobre el router
    cx, cy = 256, 236
    for radius, width in ((176, 30), (120, 30), (64, 30)):
        d.arc(
            [s(cx - radius), s(cy - radius), s(cx + radius), s(cy + radius)],
            start=225,
            end=315,
            fill=arc_color,
            width=s(width),
        )
    d.ellipse([s(cx - 20), s(cy - 20), s(cx + 20), s(cy + 20)], fill=arc_color)

    # Cuerpo del router
    d.rounded_rectangle([s(56), s(286), s(456), s(446)], radius=s(44), fill=ORANGE)
    # Franja frontal más oscura con los LED
    d.rounded_rectangle([s(56), s(386), s(456), s(446)], radius=s(44), fill=ORANGE_DARK)
    d.rectangle([s(56), s(386), s(456), s(410)], fill=ORANGE_DARK)
    for i, x in enumerate((116, 166, 216)):
        r = 13 if i else 15
        d.ellipse([s(x - r), s(416 - r), s(x + r), s(416 + r)], fill=WHITE)
    # Ranura de ventilación
    d.rounded_rectangle([s(276), s(406), s(406), s(426)], radius=s(10), fill=WHITE)
    # Patas
    for x in (120, 352):
        d.rounded_rectangle([s(x), s(446), s(x + 40), s(470)], radius=s(8), fill=ORANGE_DARK)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, arc_color in (("", (60, 60, 60, 255)), ("dark_", (235, 235, 235, 255))):
        big = _draw(arc_color)
        for name, px in (("icon.png", 256), ("icon@2x.png", 512)):
            big.resize((px, px), Image.Resampling.LANCZOS).save(OUT / f"{prefix}{name}", optimize=True)
    print(f"Iconos generados en {OUT}")


if __name__ == "__main__":
    main()
