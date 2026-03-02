"""Generate OGP image (1200x630) for PaleBlueSearch."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
OUT = Path(__file__).resolve().parents[2] / "frontend/src/frontend/static/ogp.png"

# Brand colors (Sky palette)
BG_TOP = (224, 242, 254)  # #e0f2fe Sky 100
BG_BOTTOM = (186, 230, 253)  # #bae6fd Sky 200
ACCENT = (14, 165, 233)  # #0ea5e9 Sky 500
TEXT_COLOR = (12, 74, 110)  # #0c4a6e Sky 900
SUB_COLOR = (100, 116, 139)  # #64748b Slate 500


def gradient(draw: ImageDraw.ImageDraw) -> None:
    for y in range(HEIGHT):
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * y / HEIGHT)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * y / HEIGHT)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * y / HEIGHT)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def draw_magnifier(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    r = size // 2
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=max(size // 8, 4)
    )
    offset = int(r * 0.7)
    handle_len = int(size * 0.4)
    draw.line(
        [cx + offset, cy + offset, cx + offset + handle_len, cy + offset + handle_len],
        fill=ACCENT,
        width=max(size // 8, 4),
    )


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    gradient(draw)

    # Magnifier icon
    draw_magnifier(draw, 200, HEIGHT // 2 - 20, 120)

    # Text
    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72
        )
        sub_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        )
    except OSError:
        title_font = ImageFont.load_default(72)
        sub_font = ImageFont.load_default(32)

    draw.text(
        (340, HEIGHT // 2 - 80), "PaleBlueSearch", fill=TEXT_COLOR, font=title_font
    )
    draw.text(
        (340, HEIGHT // 2 + 20),
        "BM25 + Vector Hybrid Search Engine",
        fill=SUB_COLOR,
        font=sub_font,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT), "PNG", optimize=True)
    print(f"Generated: {OUT}")


if __name__ == "__main__":
    main()
