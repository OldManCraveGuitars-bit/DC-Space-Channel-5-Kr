"""Conservative Shift-JIS discovery with byte offsets for review and editing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .disc import GDImage

LEAD = rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc])"
JP_BYTE = rb"(?:" + LEAD + rb"|[\xa1-\xdf])"
JP_SEQUENCE = re.compile(JP_BYTE + rb"(?:[\x20-\x7e]|" + JP_BYTE + rb")*")
SCANNED_SUFFIXES = {".BIN", ".RB", ".POF", ".FPB", ".MPB", ".MSB", ".DA"}


def japanese_count(text: str) -> int:
    return sum(("\u3040" <= c <= "\u30ff") or ("\u3400" <= c <= "\u9fff")
               or ("\uff61" <= c <= "\uff9f") for c in text)


def candidates(data: bytes, name: str):
    seen = set()
    for match in JP_SEQUENCE.finditer(data):
        start, end = match.span()
        raw = match.group()
        if len(raw) > 512:
            continue
        try:
            value = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        value = value.strip()
        if japanese_count(value) < 2:
            continue
        # CJK ranges in arbitrary bytes decode surprisingly often. Require
        # either kana or a plausible short text terminated by a zero byte.
        has_kana = any("\u3040" <= c <= "\u30ff" for c in value)
        zero_terminated = end < len(data) and data[end] == 0
        if not has_kana and not (zero_terminated and len(value) <= 80):
            continue
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        yield {"id": hashlib.sha1(f"{name}:{start}:{raw.hex()}".encode()).hexdigest()[:16],
               "file": name, "offset": start, "length": len(raw),
               "source": value, "translation": "", "status": "needs_review",
               "encoding": "cp932", "bytes_hex": raw.hex(),
               "confidence": "candidate", "zero_terminated": zero_terminated}


def extract_text(image: GDImage, output: Path):
    all_records = []
    for entry in image.entries():
        if entry.suffix not in SCANNED_SUFFIXES:
            continue
        data = image.read(entry.lba, entry.size)
        all_records.extend(candidates(data, entry.name))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for item in all_records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return all_records
