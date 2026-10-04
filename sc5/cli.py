from __future__ import annotations

import argparse
import json
from pathlib import Path

from .assets import afs_members, decode_pvr, encode_vq_like, image_catalog, media_catalog, pvm_members
from .disc import GDImage, write_manifest
from .text import extract_text
from .paths import project_root

DEFAULT_DISC = Path(r"C:\CODEX\roms\DC\Space Channel 5 (Japan)")
DEFAULT_DATA = project_root() / "data"


def find_entry(image, name):
    try:
        return next(e for e in image.entries() if e.name.upper() == name.upper())
    except StopIteration:
        raise SystemExit(f"Disc file not found: {name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Space Channel 5 Korean localization workbench")
    parser.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="Build file, audio, image and text catalogs")
    sub.add_parser("scan-binary", help="Experimental Shift-JIS byte scan; results are unverified")
    x = sub.add_parser("extract", help="Extract one original file without modifying the disc")
    x.add_argument("name")
    x.add_argument("output", type=Path)
    x = sub.add_parser("extract-voice", help="Extract one AFS member")
    x.add_argument("archive")
    x.add_argument("index", type=int)
    x.add_argument("output", type=Path)
    x = sub.add_parser("preview-image", help="Decode a PVR or PVM member to PNG")
    x.add_argument("name")
    x.add_argument("output", type=Path)
    x.add_argument("--member", type=int, default=0)
    x = sub.add_parser("pack-image", help="Encode a replacement PNG using a PVR as template")
    x.add_argument("name")
    x.add_argument("png", type=Path)
    x.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    with GDImage(args.disc) as image:
        if args.command == "index":
            m = write_manifest(image, DEFAULT_DATA / "disc.json")
            a = media_catalog(image, DEFAULT_DATA / "media.json")
            i = image_catalog(image, DEFAULT_DATA / "images.json")
            print(json.dumps({"files": len(m["files"]), "audio": len(a["audio"]),
                              "videos": len(a["videos"]), "images": len(i)}, ensure_ascii=False))
        elif args.command == "scan-binary":
            t = extract_text(image, DEFAULT_DATA / "unverified_binary_scan.jsonl")
            print(f"{len(t)} unverified byte sequences; most are false positives")
        elif args.command == "extract":
            image.export(find_entry(image, args.name), args.output)
            print(args.output)
        elif args.command == "extract-voice":
            e = find_entry(image, args.archive)
            data = image.read(e.lba, e.size)
            members = afs_members(data, e.name)
            member = members[args.index]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data[member["offset"]:member["offset"] + member["size"]])
            print(args.output)
        elif args.command == "preview-image":
            e = find_entry(image, args.name)
            data = image.read(e.lba, e.size)
            if e.suffix == ".PVM":
                member = pvm_members(data, e.name)[args.member]
                data = data[member["offset"]:member["offset"] + member["size"]]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            decode_pvr(data).save(args.output)
            print(args.output)
        elif args.command == "pack-image":
            from PIL import Image
            e = find_entry(image, args.name)
            if e.suffix != ".PVR":
                raise SystemExit("pack-image currently supports standalone PVR files")
            original = image.read(e.lba, e.size)
            replacement = Image.open(args.png)
            packed = encode_vq_like(original, replacement)
            if len(packed) != len(original):
                raise SystemExit("Packed image size changed")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(packed)
            print(args.output)


if __name__ == "__main__":
    main()
