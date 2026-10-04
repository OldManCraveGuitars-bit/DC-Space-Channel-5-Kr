"""Wrap CPRO translations by measured glyph width without removing content."""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

from PIL import ImageFont
from sc5.render_cpro import BLUEROAD, render_blueroad_at_24

CLOSING = ",.!?;:)]}」』、。！？"
OPENING = "([{「『"


def char_advance(char: str, font, advance: int) -> int:
    fullwidth = (unicodedata.category(char).startswith("L")
                 and unicodedata.east_asian_width(char) in ("W", "F"))
    return advance if fullwidth else round(font.getlength(char)) + 2


def _wrap_paragraph(text: str, advance: int, max_lines: int):
    text = re.sub(r"\s+", " ", text).strip()
    font = ImageFont.truetype(str(BLUEROAD), 22)
    widths = [0]
    for char in text:
        widths.append(widths[-1] + char_advance(char, font, advance))

    @lru_cache(None)
    def solve(start, remaining_lines):
        if start >= len(text):
            return (0, 0, 0), ()
        if remaining_lines <= 0:
            return None
        best = None
        for end in range(start + 1, len(text) + 1):
            width = widths[end] - widths[start]
            if width > 382:
                break
            if text[end - 1].isspace() or text[end - 1] in OPENING:
                continue
            next_start = end
            while next_start < len(text) and text[next_start].isspace():
                next_start += 1
            if next_start < len(text) and text[next_start] in CLOSING:
                continue
            if end < len(text) and text[end - 1].isascii() and text[end].isascii()                     and text[end - 1].isalnum() and text[end].isalnum():
                continue
            remaining = solve(next_start, remaining_lines - 1)
            if remaining is None:
                continue
            natural = (end == len(text) or next_start > end
                       or text[end - 1] in ",.!?;:、。！？")
            score = (remaining[0][0] + (0 if natural else 1),
                     remaining[0][1] + 1,
                     remaining[0][2] + ((382 - width) ** 2 if end < len(text) else 0))
            candidate = score, (text[start:end],) + remaining[1]
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best

    answer = solve(0, max_lines)
    if answer is None:
        raise ValueError("No valid wrapping for text")
    lines = list(answer[1])
    if re.sub(r"\s", "", "\n".join(lines)) != re.sub(r"\s", "", text):
        raise AssertionError("Wrapping changed translation content")
    return answer[0], lines


def wrap_paragraph(text: str, advance: int, max_lines: int = 8) -> list[str]:
    return _wrap_paragraph(text, advance, max_lines)[1]


def layout_card(title: str, body: str) -> tuple[str, int]:
    candidates = []
    for advance in (26, 25, 24):
        try:
            title_score, title_lines = _wrap_paragraph(title, advance, 2)
            body_score, body_lines = _wrap_paragraph(body, advance, 8 - len(title_lines))
            text = "\n".join(title_lines + body_lines)
            render_blueroad_at_24(text, advance)
        except ValueError:
            continue
        score = (title_score[0] + body_score[0], -advance,
                 len(title_lines) + len(body_lines))
        candidates.append((score, text, advance))
    if candidates:
        _, text, advance = min(candidates)
        return text, advance
    raise ValueError("Translation does not fit the original CPRO area; do not shorten its meaning")
