"""Generate consistent macOS (.icns), Windows (.ico), PNG, and Android mipmap icons
from the exact Finance Pulse Analytics brand mark geometry (viewBox 0 0 28 28).
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Exact geometry matching static/favicon.svg & templates/_icons.html (28x28 grid)
BG_HEX = (29, 29, 31, 255)          # #1D1D1F
BORDER_HEX = (255, 255, 255, 34)    # rgba(255,255,255,0.13)
WHITE = (255, 255, 255, 255)
BEACON_BLUE = (59, 155, 255, 255)   # #3B9BFF

PULSE_POINTS = [
    (5.5, 16.5),
    (9.2, 16.5),
    (11.6, 10.5),
    (14.8, 19.2),
    (17.9, 8.8),
    (20.1, 14.5),
    (22.5, 14.5),
]
BEACON_CENTER = (22.5, 14.5)


def render_brand_icon(size: int, full_bleed: bool = False, transparent_bg: bool = False) -> Image.Image:
    """Render crisp 4x supersampled Finance Pulse icon at `size x size`."""
    scale_factor = 4
    canvas_size = size * scale_factor
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if not transparent_bg:
        # Outer padding: keep slight native macOS squircle margin (0.5/28) unless full_bleed
        pad = 0.0 if full_bleed else (0.5 / 28.0) * canvas_size
        rect_end = canvas_size - pad
        radius = 0 if full_bleed else (7.5 / 28.0) * canvas_size

        draw.rounded_rectangle(
            [pad, pad, rect_end, rect_end],
            radius=radius,
            fill=BG_HEX,
            outline=None if full_bleed else BORDER_HEX,
            width=max(1, round((0.6 / 28.0) * canvas_size)),
        )

    unit = canvas_size / 28.0
    stroke_w = max(2, round(2.0 * unit))
    cap_r = stroke_w / 2.0

    # Round-capped, round-joined polyline on 4x canvas
    pts = [(x * unit, y * unit) for x, y in PULSE_POINTS]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=WHITE, width=stroke_w)
    for x, y in pts:
        draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=WHITE)

    # Beacon dot at tip
    bx, by = BEACON_CENTER[0] * unit, BEACON_CENTER[1] * unit
    br = 1.45 * unit
    draw.ellipse([bx - br, by - br, bx + br, by + br], fill=BEACON_BLUE)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def _write_icns_fallback(base_img: Image.Image, target_icns: Path) -> None:
    """Write an .icns container directly from PNG representations (cross-platform fallback)."""
    # macOS icon type codes backed by PNG payloads
    entries = [
        (b"ic07", 128),
        (b"ic08", 256),
        (b"ic09", 512),
        (b"ic10", 1024),
        (b"ic11", 32),
        (b"ic12", 64),
        (b"ic13", 256),
        (b"ic14", 512),
    ]
    from io import BytesIO

    blocks = []
    for ostype, dim in entries:
        buf = BytesIO()
        resized = base_img.resize((dim, dim), Image.Resampling.LANCZOS)
        resized.save(buf, format="PNG")
        payload = buf.getvalue()
        blocks.append(ostype + struct.pack(">I", len(payload) + 8) + payload)
    body = b"".join(blocks)
    header = b"icns" + struct.pack(">I", len(body) + 8)
    target_icns.write_bytes(header + body)


def build_desktop_icons(assets_dir: Path = ASSETS_DIR) -> tuple[Path, Path, Path]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    master_1024 = render_brand_icon(1024)
    png_1024 = assets_dir / "icon_1024.png"
    master_1024.save(png_1024, format="PNG")

    # Also save clean 256 & 512 PNG previews for docs / Android reuse
    render_brand_icon(512).save(assets_dir / "icon_512.png", format="PNG")
    render_brand_icon(256).save(assets_dir / "icon_256.png", format="PNG")

    # Windows multi-resolution .ico
    ico_path = assets_dir / "finance_pulse.ico"
    master_1024.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # macOS .icns (prefer native iconutil on macOS, fallback on Linux/Windows)
    icns_path = assets_dir / "finance_pulse.icns"
    iconset_dir = assets_dir / "finance_pulse.iconset"
    if sys.platform == "darwin" and shutil.which("iconutil"):
        if iconset_dir.exists():
            shutil.rmtree(iconset_dir)
        iconset_dir.mkdir(parents=True)
        for dim, name in [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]:
            render_brand_icon(dim).save(iconset_dir / name, format="PNG")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=True,
        )
        shutil.rmtree(iconset_dir, ignore_errors=True)
    else:
        _write_icns_fallback(master_1024, icns_path)

    return png_1024, icns_path, ico_path


def build_android_mipmaps(res_dir: Path) -> None:
    """Emit standard launcher mipmaps and adaptive foregrounds into Android res/."""
    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    fg_densities = {
        "mipmap-mdpi": 108,
        "mipmap-hdpi": 162,
        "mipmap-xhdpi": 216,
        "mipmap-xxhdpi": 324,
        "mipmap-xxxhdpi": 432,
    }
    for folder, dim in densities.items():
        out_dir = res_dir / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        icon = render_brand_icon(dim)
        icon.save(out_dir / "ic_launcher.png", format="PNG")
        icon.save(out_dir / "ic_launcher_round.png", format="PNG")

    # Adaptive icon foreground (108dp canvas with centered pulse artwork over #1D1D1F background)
    for folder, dim in fg_densities.items():
        out_dir = res_dir / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        fg = render_brand_icon(round(dim * 0.68), transparent_bg=True)
        canvas = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
        offset = (dim - fg.width) // 2
        canvas.paste(fg, (offset, offset))
        canvas.save(out_dir / "ic_launcher_foreground.png", format="PNG")


if __name__ == "__main__":
    png, icns, ico = build_desktop_icons()
    print(f"Generated: {png}, {icns}, {ico}")
    if "--android" in sys.argv:
        android_res = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"
        build_android_mipmaps(android_res)
        print(f"Generated Android mipmaps in {android_res}")
