"""Render editable text into the fixed UV rectangles of stage caption atlases."""
from __future__ import annotations

import unicodedata
from PIL import Image, ImageDraw, ImageFont


def render_labels(original, labels, font_path):
    """Keep each original 26px row and use its original English glyphs."""
    result = original.convert("RGBA").copy()
    font = ImageFont.truetype(str(font_path), 22)
    for label in labels:
        x, y, width, height = label["region"]
        if height != 26 or not (0 <= x < x + width <= result.width):
            raise ValueError("Stage caption rectangle is invalid")
        text = label["korean"]
        source = label.get("source_text", label["japanese"])
        source_x = label.get("source_x", x)
        latin = {}
        for index, char in enumerate(source):
            char = unicodedata.normalize("NFKC", char)
            if len(char) == 1 and char.isascii() and char.isalnum():
                left = source_x + index * 26
                tile = original.crop((left, y, left + 26, y + 26)).convert("RGBA")
                bounds = tile.getchannel("A").getbbox()
                if bounds:
                    latin[char] = (tile.crop((bounds[0], 0, bounds[2], 26)), bounds[2] - bounds[0])
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
        for spacing in (24, 23, 22):
            measured = sum(advance(c, spacing) for c in text)
            if measured <= available:
                break
        else:
            raise ValueError(f"Translation exceeds its original UV width ({width}px): {text}")
        row = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        mask = Image.new("L", (width, height), 0)
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
                draw.text((left - bounds[0], 20), char, font=font, fill=255, anchor="ls")
            pen += step
        mask = mask.point(lambda p: 255 if p >= 96 else 0)
        row.paste((255, 255, 255, 255), (0, 0, width, height), mask)
        if fixed:
            fx, fw = fixed["x"], fixed["width"]
            row.paste(original.crop((fx, y, fx + fw, y + height)), (fx - x, 0))
        result.paste(row, (x, y))
    return result
