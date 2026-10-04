"""Render editable Korean CPRO textures with selectable bitmap fonts."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import unicodedata

from PIL import Image, ImageDraw, ImageFont

from .bdf_font import draw_bdf, load_bdf
from .paths import project_root, resource_path

ROOT = project_root()
FONT = ROOT / "assets" / "fonts" / "16x16" / "NanumGothicCoding-Regular.ttf"
MARUMINYA = ROOT / "assets" / "fonts" / "maruminya12" / "x12y12pxMaruMinyaHangul.bdf"
NEODGM_DIR = ROOT / "assets" / "fonts" / "neodgm16"
NEODGM_TTF = NEODGM_DIR / "font-45065ee8eedf7051.ttf"
NEODGM_BIN = NEODGM_DIR / "font-45065ee8eedf7051.bin"
NEODGM_MAP = NEODGM_DIR / "font-45065ee8eedf7051_glyph_map.json"
GALMURI14 = ROOT / "assets" / "fonts" / "galmuri14" / "Galmuri14.bdf"
MONEYGRAPHY_PIXEL = ROOT / "assets" / "fonts" / "moneygraphy" / "Moneygraphy-Pixel.ttf"
GEURIMILGI = ROOT / "assets" / "fonts" / "hakgyoansim-geurimilgi" / "Hakgyoansim-Geurimilgi.ttf"
BLUEROAD = resource_path("assets/fonts/yeongdeok-blueroad/Yeongdeok-Blueroad.ttf")


def render(text: str) -> Image.Image:
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    mask = Image.new("L", (512, 512), 0)
    draw = ImageDraw.Draw(mask)
    font = ImageFont.truetype(str(FONT), 16)
    y = 2
    for line in text.splitlines():
        if draw.textbbox((0, y), line, font=font)[2] > 384:
            raise ValueError(f"Line exceeds the original text area: {line}")
        draw.text((2, y), line, fill=255, font=font, stroke_width=0)
        y += 20
    if y > 205:
        raise ValueError("Text exceeds the original CPRO area (205 px)")
    # 1-bit output preserves the existing white-on-transparent game style.
    pixels = mask.point(lambda p: 255 if p >= 128 else 0)
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), pixels)
    return image


def render_maruminya(text: str) -> Image.Image:
    return draw_bdf(text, MARUMINYA)


def render_neodgm(text: str) -> Image.Image:
    glyph_map = json.loads(NEODGM_MAP.read_text(encoding="utf-8"))
    binary = NEODGM_BIN.read_bytes()
    font = ImageFont.truetype(str(NEODGM_TTF), 16)
    mask = Image.new("1", (512, 512), 0)
    draw = ImageDraw.Draw(mask)
    pixels = mask.load()
    y = 2
    for line in text.splitlines():
        x = 2
        for char in line:
            if "\uac00" <= char <= "\ud7a3":
                if char not in glyph_map:
                    raise ValueError(f"Hangul glyph missing from selected 2350-set: {char}")
                tile = binary[glyph_map[char] * 32:(glyph_map[char] + 1) * 32]
                for row in range(16):
                    bits = int.from_bytes(tile[row * 2:row * 2 + 2], "big")
                    for col in range(16):
                        if bits & (1 << (15 - col)):
                            pixels[x + col, y + row] = 1
                x += 16
            else:
                draw.text((x, y), char, font=font, fill=1)
                x += round(font.getlength(char))
        if x > 384:
            raise ValueError(f"Line exceeds original text area: {line}")
        y += 20
    if y > 205:
        raise ValueError("Text exceeds original CPRO area")
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), mask.convert("L").point(lambda p: 255 if p else 0))
    return image


def render_neodgm_at_24(text: str) -> Image.Image:
    """Place the selected 16x16 glyph source in the original 24px cell."""
    glyph_map = json.loads(NEODGM_MAP.read_text(encoding="utf-8"))
    binary = NEODGM_BIN.read_bytes()
    font = ImageFont.truetype(str(NEODGM_TTF), 16)
    mask = Image.new("L", (512, 512), 0)
    y = 2
    for line in text.splitlines():
        x = 2
        for char in line:
            tile = Image.new("L", (16, 16), 0)
            if "\uac00" <= char <= "\ud7a3":
                if char not in glyph_map:
                    raise ValueError(f"Hangul glyph missing from selected 2350-set: {char}")
                data = binary[glyph_map[char] * 32:(glyph_map[char] + 1) * 32]
                px = tile.load()
                for row in range(16):
                    bits = int.from_bytes(data[row * 2:row * 2 + 2], "big")
                    for col in range(16):
                        if bits & (1 << (15 - col)):
                            px[col, row] = 255
                advance = 26
            else:
                ImageDraw.Draw(tile).text((0, 0), char, font=font, fill=255)
                advance = round(font.getlength(char) * 1.5) + 2
            enlarged = tile.resize((24, 24), Image.Resampling.NEAREST)
            mask.paste(enlarged, (x, y), enlarged)
            x += advance
        if x > 384:
            raise ValueError(f"Line exceeds original text area: {line}")
        y += 26
    if mask.getbbox() and mask.getbbox()[3] > 210:
        raise ValueError("Text exceeds original CPRO area")
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), mask)
    return image


def render_galmuri14_at_24(text: str) -> Image.Image:
    """Fit Galmuri14's native bitmap into the original 24px CPRO cell."""
    glyphs = load_bdf(GALMURI14, set(text))
    mask = Image.new("L", (512, 512), 0)
    for line_number, line in enumerate(text.splitlines()):
        x = 2
        y = line_number * 26
        for char in line:
            glyph = glyphs[char]
            tile = Image.new("L", (16, 17), 0)
            pixels = tile.load()
            row_bits = ((glyph.width + 7) // 8) * 8
            top = 17 - (glyph.height + glyph.yoff)
            for row, bits in enumerate(glyph.rows):
                for col in range(glyph.width):
                    px, py = glyph.xoff + col, top + row
                    if 0 <= px < 16 and 0 <= py < 17 and bits & (1 << (row_bits - 1 - col)):
                        pixels[px, py] = 255
            mask.paste(tile.resize((24, 24), Image.Resampling.NEAREST), (x, y))
            x += 26 if ord(char) > 127 else round(glyph.advance * 1.5) + 2
        if x > 384:
            raise ValueError(f"Line exceeds original text area: {line}")
    if mask.getbbox() and mask.getbbox()[3] > 210:
        raise ValueError("Text exceeds original CPRO area")
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), mask)
    return image


def render_ttf_at_24(text: str, font_path: Path, font_size: int, threshold: int) -> Image.Image:
    """Rasterize a TTF within CPRO's original 24px cells and 26px lines."""
    font = ImageFont.truetype(str(font_path), font_size)
    mask = Image.new("L", (512, 512), 0)
    for line_number, line in enumerate(text.splitlines()):
        x = 2
        y = line_number * 26 + 1
        for char in line:
            scratch = Image.new("L", (40, 40), 0)
            ImageDraw.Draw(scratch).text((0, 0), char, font=font, fill=255, anchor="lt")
            bounds = scratch.getbbox()
            if bounds:
                glyph = scratch.crop(bounds).point(lambda p: 255 if p >= threshold else 0)
                width, height = glyph.size
                if width > 24 or height > 24:
                    raise ValueError(f"Glyph exceeds 24px cell: {char}")
                cell = Image.new("L", (24, 24), 0)
                cell.paste(glyph, ((24 - width) // 2, (24 - height) // 2))
                mask.paste(cell, (x, y))
            x += 26 if ord(char) > 127 else round(font.getlength(char)) + 2
        if x > 384:
            raise ValueError(f"Line exceeds original text area: {line}")
    if mask.getbbox() and mask.getbbox()[3] > 210:
        raise ValueError("Text exceeds original CPRO area")
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), mask)
    return image


def render_moneygraphy_at_24(text: str) -> Image.Image:
    return render_ttf_at_24(text, MONEYGRAPHY_PIXEL, 22, 128)


def render_geurimilgi_at_24(text: str) -> Image.Image:
    return render_ttf_at_24(text, GEURIMILGI, 24, 64)


def render_blueroad_at_24(text: str, fullwidth_advance: int = 26, font_path=None) -> Image.Image:
    """Keep the font baseline and natural punctuation width in 24px CPRO text."""
    if fullwidth_advance not in (24, 25, 26):
        raise ValueError("Fullwidth advance must be 24, 25, or 26 pixels")
    font = ImageFont.truetype(str(font_path or BLUEROAD), 22)
    mask = Image.new("L", (512, 512), 0)
    draw = ImageDraw.Draw(mask)
    for line_number, line in enumerate(text.splitlines()):
        x = 2
        baseline = 19 + line_number * 26
        for char in line:
            bounds = font.getbbox(char, anchor="ls")
            glyph_width = bounds[2] - bounds[0]
            fullwidth_letter = (
                unicodedata.category(char).startswith("L")
                and unicodedata.east_asian_width(char) in ("W", "F")
            )
            ink_left = x + (24 - glyph_width) // 2 if fullwidth_letter else x
            draw.text((ink_left - bounds[0], baseline), char,
                      font=font, fill=255, anchor="ls")
            x += fullwidth_advance if fullwidth_letter else round(font.getlength(char)) + 2
        if x > 384:
            raise ValueError(f"Line exceeds original text area: {line}")
    mask = mask.point(lambda value: 255 if value >= 96 else 0)
    bounds = mask.getbbox()
    if bounds and (bounds[2] > 384 or bounds[3] > 210):
        raise ValueError("Text exceeds original CPRO area")
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0, 512, 512), mask)
    return image


def main():
    p = argparse.ArgumentParser()
    p.add_argument("id", help="CPRO file name, e.g. CPRO01.PVR")
    p.add_argument("text_file", type=Path)
    p.add_argument("--font", choices=("blueroad_at24", "geurimilgi_at24", "moneygraphy_pixel_at24", "galmuri14_at24", "neodgm16_at24", "neodgm16", "maruminya12", "nanum16"),
                   default="blueroad_at24")
    p.add_argument("--fullwidth-advance", type=int, choices=(24, 25, 26), default=26,
                   help="Hangul letter spacing for dense Blueroad CPRO cards")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not args.id.startswith("CPRO") or not args.id.endswith(".PVR"):
        raise SystemExit("Only CPRO textures are supported")
    out = args.output or ROOT / "assets" / "image-edits" / (args.id + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    text = args.text_file.read_text(encoding="utf-8").strip()
    renderer = {"blueroad_at24": render_blueroad_at_24,
                "geurimilgi_at24": render_geurimilgi_at_24,
                "moneygraphy_pixel_at24": render_moneygraphy_at_24,
                "galmuri14_at24": render_galmuri14_at_24,
                "neodgm16_at24": render_neodgm_at_24, "neodgm16": render_neodgm,
                "maruminya12": render_maruminya,
                "nanum16": render}[args.font]
    image = (render_blueroad_at_24(text, args.fullwidth_advance)
             if args.font == "blueroad_at24" else renderer(text))
    image.save(out)
    print(out)


if __name__ == "__main__":
    main()
