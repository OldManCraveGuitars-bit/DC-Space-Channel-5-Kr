"""Read native BDF bitmap glyphs so 12x12 MaruMinya stays pixel exact."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class Glyph:
    width: int
    height: int
    xoff: int
    yoff: int
    advance: int
    rows: tuple[int, ...]


def load_bdf(path: Path, characters: set[str]) -> dict[str, Glyph]:
    wanted = {ord(c) for c in characters}
    glyphs = {}
    current = {}
    rows = []
    in_bitmap = False
    with path.open("r", encoding="utf-8") as file:
        for raw in file:
            line = raw.strip()
            if line.startswith("STARTCHAR "):
                current, rows, in_bitmap = {}, [], False
            elif line.startswith("ENCODING "):
                current["encoding"] = int(line.split()[1])
            elif line.startswith("DWIDTH "):
                current["advance"] = int(line.split()[1])
            elif line.startswith("BBX "):
                current["box"] = tuple(map(int, line.split()[1:5]))
            elif line == "BITMAP":
                in_bitmap = True
            elif line == "ENDCHAR":
                codepoint = current.get("encoding")
                if codepoint in wanted:
                    w, h, x, y = current["box"]
                    glyphs[chr(codepoint)] = Glyph(w, h, x, y, current["advance"], tuple(rows))
                in_bitmap = False
            elif in_bitmap:
                rows.append(int(line, 16))
    missing = characters - glyphs.keys() - {"\n", "\r"}
    if missing:
        raise ValueError(f"Missing BDF glyphs: {''.join(sorted(missing))}")
    return glyphs


def draw_bdf(text: str, path: Path, *, area_width: int = 384,
             area_height: int = 205, canvas_size=(512, 512),
             line_height: int = 15) -> Image.Image:
    glyphs = load_bdf(path, set(text))
    image = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    pixels = image.load()
    y = 2
    for line in text.splitlines():
        x = 2
        for char in line:
            glyph = glyphs[char]
            width_bits = ((glyph.width + 7) // 8) * 8
            top = y + 12 - (glyph.height + glyph.yoff)
            for row, value in enumerate(glyph.rows):
                for col in range(glyph.width):
                    if value & (1 << (width_bits - 1 - col)):
                        px, py = x + glyph.xoff + col, top + row
                        if 0 <= px < canvas_size[0] and 0 <= py < canvas_size[1]:
                            pixels[px, py] = (255, 255, 255, 255)
            x += glyph.advance
        if x > area_width:
            raise ValueError(f"Line exceeds original text area: {line}")
        y += line_height
    if y > area_height:
        raise ValueError("Text exceeds original CPRO area")
    return image
