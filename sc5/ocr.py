"""Extract draft Japanese copy from the 79 CPRO information textures."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageOps

from .assets import decode_pvr
from .cli import DEFAULT_DATA, DEFAULT_DISC
from .disc import GDImage

ROOT = Path(__file__).resolve().parents[1]
TESSERACT = ROOT / "tools" / "Tesseract-OCR" / "tesseract.exe"


def ocr_cpro(image: Image.Image) -> str:
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        return ""
    # White pixel text on transparent background becomes black on white.
    crop = ImageOps.invert(alpha.crop(box))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.NEAREST)
    stream = BytesIO()
    crop.save(stream, format="PNG")
    result = subprocess.run([str(TESSERACT), "stdin", "stdout", "-l", "jpn",
                             "--psm", "6"], input=stream.getvalue(), capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    p.add_argument("--output", type=Path, default=DEFAULT_DATA / "text_review.jsonl")
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["id"])
    with GDImage(args.disc) as disc, args.output.open("a", encoding="utf-8", newline="\n") as out:
        for entry in disc.entries():
            if not entry.name.startswith("CPRO") or entry.suffix != ".PVR" or entry.name in done:
                continue
            image = decode_pvr(disc.read(entry.lba, entry.size))
            japanese = ocr_cpro(image)
            record = {"id": entry.name, "image": entry.name, "source": japanese,
                      "japanese": japanese, "korean": "", "status": "ocr_draft",
                      "method": "Tesseract jpn on 4x nearest-neighbor alpha mask"}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(entry.name, len(japanese), flush=True)


if __name__ == "__main__":
    main()
