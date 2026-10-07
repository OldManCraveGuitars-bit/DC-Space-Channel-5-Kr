"""Render editable text into the fixed UV rectangles of stage caption atlases."""
from __future__ import annotations

import unicodedata
from PIL import Image, ImageDraw, ImageFont


def render_labels(original, labels, font_path):
    """Keep each original 26px row and use its original English glyphs."""
    result = original.convert("RGBA").copy()
    # Reflowed UI messages retain the original cells as the source for A/B/5.
    # Clear every old cell before painting so moved rows cannot erase each other.
    for label in labels:
        if label.get('source_region'):
            sx, sy, sw, sh = label['source_region']
            result.paste((0, 0, 0, 0), (sx, sy, sx + sw, sy + sh))
    for label in labels:
        x, y, width, height = label["region"]
        font_size = int(label.get('font_size', 22))
        font = ImageFont.truetype(str(font_path), font_size)
        fine_font = ImageFont.truetype(str(font_path), font_size * 4)
        baseline = int(label.get('baseline', 20))
        if height < font_size or not (0 <= x < x + width <= result.width) or not (0 <= y < y + height <= result.height):
            raise ValueError("Stage caption rectangle is invalid")
        text = label["korean"]
        source = label.get("source_text", label["japanese"])
        source_x = label.get("source_x", x)
        source_y = label.get("source_y", y)
        latin_scale = float(label.get('latin_scale', 1))
        latin = {}
        for index, char in enumerate(source):
            char = unicodedata.normalize("NFKC", char)
            if len(char) == 1 and char.isascii() and char.isalnum():
                left = source_x + index * 26
                tile = original.crop((left, source_y, left + 26, source_y + 26)).convert("RGBA")
                bounds = tile.getchannel("A").getbbox()
                if bounds:
                    tile = tile.crop((bounds[0], 0, bounds[2], 26))
                    if latin_scale != 1:
                        size = (max(1, round(tile.width * latin_scale)), round(26 * latin_scale))
                        alpha = tile.getchannel('A').resize(size, Image.Resampling.BOX)
                        alpha = alpha.point(lambda p: 0 if p < 64 else 85 if p < 112 else 170 if p < 160 else 255)
                        tile = Image.new('RGBA', size, (255, 255, 255, 0))
                        tile.putalpha(alpha)
                    latin[char] = (tile, tile.width)
        fixed = label.get("fixed_english")
        if fixed:
            suffix = fixed["text"]
            if not text.endswith(suffix):
                raise ValueError(f"Keep the original English suffix: {suffix}")
            text = text[:-len(suffix)].rstrip()
        def advance(char, spacing):
            if char in latin:
                return latin[char][1] + 2
            if unicodedata.category(char).startswith("L") and unicodedata.east_asian_width(char) in ("W", "F"):
                return spacing
            return round(font.getlength(char)) + 2
        available = fixed["x"] - x if fixed else width
        for spacing in label.get('spacing_candidates', (24, 23, 22)):
            measured = sum(advance(c, spacing) for c in text)
            if measured <= available:
                break
        else:
            raise ValueError(f"Translation exceeds its original UV width ({width}px): {text}")
        row = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        raster = label.get("glyph_rasterization")
        smooth = raster in {"coverage_2bit", "coverage_crisp"}
        scale = 4 if smooth else 1
        mask = Image.new("L", (width * scale, height * scale), 0)
        draw = ImageDraw.Draw(mask)
        pen = max(0, (available - measured) // 2) if label.get("align") == "center" else 1
        for char in text:
            step = advance(char, spacing)
            if char in latin:
                tile, _ = latin[char]
                row.paste(tile, (pen, 0))
            else:
                bounds = font.getbbox(char, anchor="ls")
                wide = unicodedata.category(char).startswith("L") and unicodedata.east_asian_width(char) in ("W", "F")
                left = pen + (spacing - (bounds[2] - bounds[0])) // 2 if wide else pen
                if smooth:
                    fine_bounds = fine_font.getbbox(char, anchor="ls")
                    fine_left = pen * scale + (spacing * scale - (fine_bounds[2] - fine_bounds[0])) // 2 if wide else pen * scale
                    # Strengthen thin strokes at subpixel scale so their
                    # interiors remain white after downsampling and filtering.
                    stroke = int(label.get("glyph_stroke_quarters", 0))
                    if not 0 <= stroke <= 2:
                        raise ValueError("Glyph stroke must be 0..2 quarter pixels")
                    draw.text((fine_left - fine_bounds[0], baseline * scale), char,
                              font=fine_font, fill=255, anchor="ls", stroke_width=stroke)
                else:
                    draw.text((left - bounds[0], baseline), char, font=font, fill=255, anchor="ls")
            pen += step
        if smooth:
            # Four alpha levels give smoother strokes while the complete 2x2
            # white-text alphabet still fits a 256-entry VQ codebook exactly.
            if raster == "coverage_crisp":
                # Area coverage has no ringing outside the font outline.
                # Keep narrow edge coverage and a solid white stroke interior.
                mask = mask.resize((width, height), Image.Resampling.BOX)
                mask = mask.point(lambda p: 0 if p < 64 else 85 if p < 112 else 170 if p < 160 else 255)
            else:
                mask = mask.resize((width,height),Image.Resampling.LANCZOS)
                mask = mask.point(lambda p: min(255,((p+42)//85)*85))
            layer = Image.new("RGBA",(width,height),(255,255,255,0))
            layer.putalpha(mask)
            row = Image.alpha_composite(row,layer)
        else:
            mask = mask.point(lambda p: 255 if p >= 96 else 0)
            row.paste((255, 255, 255, 255), (0, 0, width, height), mask)
        if fixed:
            fx, fw = fixed["x"], fixed["width"]
            row.paste(original.crop((fx, y, fx + fw, y + height)), (fx - x, 0))
        result.paste(row, (x, y))
    return result
