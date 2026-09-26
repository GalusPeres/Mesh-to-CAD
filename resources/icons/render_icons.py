"""Render icon.png and icon.ico from the shapes of icon.svg.

The mark is two flat shapes: a grey triangle (a scan facet) and a blue square (the
CAD solid). Pillow draws them with 8x supersampling; run with the project venv:

    .venv/Scripts/python resources/icons/render_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
GREY = (0x7C, 0x80, 0x88, 255)
ACCENT = (0x2B, 0x6B, 0xD0, 255)
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(size: int) -> Image.Image:
    scale = size * 8 / 256
    image = Image.new("RGBA", (size * 8, size * 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [
            (20 * scale, 100 * scale),
            (156 * scale, 236 * scale),
            (20 * scale, 236 * scale),
        ],
        fill=GREY,
    )
    draw.rectangle([100 * scale, 20 * scale, 236 * scale, 156 * scale], fill=ACCENT)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    render(512).save(HERE / "icon.png")
    largest = render(256)
    largest.save(HERE / "icon.ico", sizes=[(size, size) for size in ICO_SIZES])


if __name__ == "__main__":
    main()
