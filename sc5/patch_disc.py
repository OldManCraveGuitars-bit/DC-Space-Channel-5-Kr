"""Apply same-length texture/SAN edits to a copied track with valid EDC/ECC."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import os
import shutil

from .cli import DEFAULT_DISC
from .disc import GDImage, PAYLOAD, SECTOR
from .sector import update_mode1, verify_mode1
from .assets import pvm_members


def patch(image: GDImage, replacements: dict[str, Path], output_track: Path,
          *, update_existing: bool = False):
    if output_track.resolve() == image.track5.resolve():
        raise ValueError("Refusing to overwrite the original track")
    entries = {e.name: e for e in image.entries()}
    changes: dict[int, bytearray] = {}
    for name, path in replacements.items():
        if name not in entries or entries[name].suffix not in (".PVR", ".PVM", ".AFS"):
            raise ValueError(f"Not a supported texture/SAN archive on disc: {name}")
        entry = entries[name]
        replacement = path.read_bytes()
        if len(replacement) != entry.size:
            raise ValueError(f"Replacement size differs: {name}")
        source = image.read(entry.lba, entry.size)
        if entry.suffix == ".PVR":
            header = source.find(b"PVRT") + 16
            if header < 16 or replacement[:header] != source[:header]:
                raise ValueError(f"PVR header/layout changed: {name}")
        elif entry.suffix == ".AFS":
            from .build_san import validate_archive
            validate_archive(source, replacement, name)
        else:
            members = pvm_members(source, name)
            if pvm_members(replacement, name) != members or not members:
                raise ValueError(f"PVM member layout changed: {name}")
            first = members[0]["offset"]
            if replacement[:first] != source[:first]:
                raise ValueError(f"PVM directory changed: {name}")
            for member in members:
                offset = member["offset"]
                if replacement[offset:offset + 16] != source[offset:offset + 16]:
                    raise ValueError(f"PVM texture header changed: {member['id']}")
        for offset in range(0, len(replacement), PAYLOAD):
            lba = entry.lba + offset // PAYLOAD
            if lba not in changes:
                changes[lba] = bytearray(image.read(lba, PAYLOAD))
            block = replacement[offset:offset + PAYLOAD]
            changes[lba][:len(block)] = block
    output_track.parent.mkdir(parents=True, exist_ok=True)
    if output_track.exists():
        if not update_existing:
            raise FileExistsError(output_track)
        if output_track.stat().st_size != image.track5.stat().st_size:
            raise ValueError("Existing output track has unexpected length")
    else:
        shutil.copyfile(image.track5, output_track)
    with output_track.open("r+b") as f:
        for lba, payload in sorted(changes.items()):
            sector_index = lba - image.track5_start
            if not 0 <= sector_index < image.track5_sectors:
                raise ValueError(f"Replacement LBA not on track 5: {lba}")
            f.seek(sector_index * SECTOR)
            original = f.read(SECTOR)
            if not verify_mode1(original):
                raise ValueError(f"Original sector fails EDC/ECC: {lba}")
            updated = update_mode1(original, payload)
            if not verify_mode1(updated):
                raise AssertionError(f"Generated sector fails EDC/ECC: {lba}")
            f.seek(sector_index * SECTOR)
            f.write(updated)
    return len(changes)


def write_cue(image: GDImage, output_track: Path, cue: Path, *, track3_override: Path | None = None):
    original = (image.cue_dir / "Space Channel 5 (Japan).cue").read_text(encoding="ascii")
    for n in (1, 2, 3, 4):
        filename = next(image.cue_dir.glob(f"*Track {n}).bin"))
        target = track3_override if n == 3 and track3_override else filename
        relative = Path(os.path.relpath(target.resolve(), cue.parent.resolve())).as_posix()
        original = original.replace(f'"{filename.name}"', f'"{relative}"')
    relative = Path(os.path.relpath(output_track.resolve(), cue.parent.resolve())).as_posix()
    original = original.replace(f'"{image.track5.name}"', f'"{relative}"')
    cue.write_text(original, encoding="ascii")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    p.add_argument("--pvr", action="append", required=True,
                   help="NAME=path to same-length replacement PVR; repeatable")
    p.add_argument("--out", type=Path, required=True, help="New track 5 BIN path")
    p.add_argument("--update", action="store_true", help="Update an existing generated track")
    args = p.parse_args()
    replacements = {}
    for spec in args.pvr:
        name, path = spec.split("=", 1)
        replacements[name] = Path(path)
    with GDImage(args.disc) as image:
        count = patch(image, replacements, args.out, update_existing=args.update)
        cue = args.out.with_suffix(".cue")
        write_cue(image, args.out.resolve(), cue)
    print(f"Patched {count} sectors; cue: {cue}")


if __name__ == "__main__":
    main()
