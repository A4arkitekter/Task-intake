from pathlib import Path

from PIL import Image, ImageDraw

from app.config import ICON_DIR, ensure_dirs

ACCENT = (196, 92, 38, 255)
PAPER = (255, 255, 255, 255)


def ensure_icons() -> None:
    ensure_dirs()
    for size in (192, 512):
        path = ICON_DIR / f"icon-{size}.png"
        if not path.exists():
            _draw_icon(path, size)


def ensure_app_icon() -> Path:
    """Windows-genveje og notifikationer vil have en .ico, ikke en .png."""
    ico = ICON_DIR / "app.ico"
    if ico.exists():
        return ico
    source = ICON_DIR / "icon-512.png"
    if not source.exists():
        _draw_icon(source, 512)
    Image.open(source).save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return ico


def _draw_icon(path: Path, size: int) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.22, fill=ACCENT)

    cx, cy = size / 2, size * 0.46
    mic_w = size * 0.18
    mic_h = size * 0.28
    draw.rounded_rectangle(
        (cx - mic_w / 2, cy - mic_h / 2, cx + mic_w / 2, cy + mic_h / 2),
        radius=mic_w / 2,
        fill=PAPER,
    )
    # yoke
    yoke_r = size * 0.2
    width = max(int(size * 0.045), 3)
    draw.arc(
        (cx - yoke_r, cy - yoke_r * 0.15, cx + yoke_r, cy + yoke_r * 1.15),
        start=10,
        end=170,
        fill=PAPER,
        width=width,
    )
    stem_x = cx
    stem_top = cy + yoke_r * 0.85
    stem_bot = size * 0.78
    draw.line((stem_x, stem_top, stem_x, stem_bot), fill=PAPER, width=width)
    draw.line((cx - size * 0.12, stem_bot, cx + size * 0.12, stem_bot), fill=PAPER, width=width)
    img.save(path, "PNG")
