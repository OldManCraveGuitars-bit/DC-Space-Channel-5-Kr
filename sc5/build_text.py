"""Build reviewed CPRO text edits into a separate Dreamcast track copy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from fontTools.ttLib import TTFont

from .assets import decode_pvr, encode_vq_like
from .cli import DEFAULT_DISC
from .disc import GDImage
from .patch_disc import patch, write_cue
from .render_cpro import BLUEROAD, ROOT, render_blueroad_at_24
from .editor_project import Project
from .build_images import pack_atlases
from .lossless_artwork import relocate_artwork
from .common_atlas_storage import repack_common
from .build_san import pack_animations


def build(disc: Path, output: Path) -> dict:
    data_dir = ROOT / "data"
    edits_path = data_dir / "edits.json"
    edits = json.loads(edits_path.read_text(encoding="utf-8"))
    text_edits = edits.get("text", {})
    policy = json.loads((data_dir / "font_policy.json").read_text(encoding="utf-8"))
    overrides = policy["cpro_layout"].get("dense_card_overrides_px", {})
    images: dict[str, object] = {}
    replacements: dict[str, bytes] = {}
    manifest = {"font": "Yeongdeok Blueroad",
                "font_sha256": hashlib.sha256(BLUEROAD.read_bytes()).hexdigest(),
                "cards": []}

    font_codepoints = TTFont(str(BLUEROAD)).getBestCmap()

    with GDImage(disc) as image:
        if output.resolve() == image.track5.resolve():
            raise ValueError("Refusing to overwrite the original track")
        entries = {entry.name: entry for entry in image.entries()}
        for name, record in sorted(text_edits.items()):
            if record.get("status") == "영어 유지":
                continue
            if not name.startswith("CPRO") or not name.endswith(".PVR"):
                continue
            stem = name[:-4]
            source_path = data_dir / "translations" / (stem + ".jp.txt")
            translation_path = data_dir / "translations" / (stem + ".txt")
            if not source_path.exists() or not translation_path.exists():
                raise FileNotFoundError(f"Missing source or translation for {name}")
            source = source_path.read_text(encoding="utf-8").strip()
            translation = translation_path.read_text(encoding="utf-8").strip()
            if not source or not translation:
                raise ValueError(f"Empty source or translation for {name}")
            if source != record.get("japanese") or translation != record.get("korean"):
                raise ValueError(f"Workbench record differs from translation files: {name}")
            advance = int(record.get("fullwidth_advance", overrides.get(name, 26)))
            missing = sorted({ord(c) for c in translation if not c.isspace() and ord(c) not in font_codepoints})
            if missing:
                raise ValueError(f"Font glyphs missing for {name}: {missing}")
            rendered = render_blueroad_at_24(translation, advance)
            entry = entries[name]
            original = image.read(entry.lba, entry.size)
            packed = encode_vq_like(original, rendered)
            if len(packed) != len(original):
                raise ValueError(f"PVR size changed: {name}")
            if decode_pvr(packed).tobytes() != rendered.tobytes():
                raise ValueError(f"PVR round trip changed pixels: {name}")
            images[name] = rendered
            replacements[name] = packed
            manifest["cards"].append({"name": name, "fullwidth_advance": advance,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "translation_sha256": hashlib.sha256(translation.encode("utf-8")).hexdigest(),
                "pvr_sha256": hashlib.sha256(packed).hexdigest()})

        if not replacements:
            raise ValueError("No translated CPRO cards to build")
        image_dir = ROOT / "assets" / "image-edits"
        pvr_dir = ROOT / "assets" / "pvr-edits"
        image_dir.mkdir(parents=True, exist_ok=True)
        pvr_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, packed in replacements.items():
            images[name].save(image_dir / (name + ".png"))
            path = pvr_dir / name
            path.write_bytes(packed)
            paths[name] = path

        atlas_paths, manifest["atlas_images"] = pack_atlases(Project(ROOT, disc), image)
        paths.update(atlas_paths)
        san_paths, manifest["SAN_animations"] = pack_animations(Project(ROOT, disc), image)
        paths.update(san_paths)
        from .movie_assets import registered_movies
        movie_paths, manifest['movie_replacements'] = registered_movies(Project(ROOT, disc))
        for row in manifest['movie_replacements']:
            entry = entries[row['name']]
            assert entry.size == row['original_size']
            assert hashlib.sha256(image.read(entry.lba,entry.size)).hexdigest() == row['original_sha256']
        paths.update(movie_paths)
        lossless = paths.pop("0GDTEX.PVR", None) if any(
            report.get("packing_mode") == "lossless_twiddled" for report in manifest["atlas_images"]) else None
        expanded_common = paths.pop('COMMON_DATA.PVM',None) if any(
            report.get('packing_mode') in {'common_uncompressed','common_compact'} for report in manifest['atlas_images']) else None

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.stem + f".building-{os.getpid()}" + output.suffix)
        track3 = output.parent / "Track3_KR.bin"
        temporary3 = track3.with_name(track3.name + f".building-{os.getpid()}")
        try:
            sectors = patch(image, paths, temporary)
            if lossless:
                relocation = relocate_artwork(image, lossless, temporary, temporary3)
                manifest["lossless_artwork"] = relocation
                sectors += relocation["track5_sectors"]
                manifest["track3"] = str(track3.resolve())
                manifest["track3_changed_sectors"] = relocation["track3_sectors"]
            if expanded_common:
                mode=next(r['packing_mode'] for r in manifest['atlas_images']
                          if r.get('packing_mode') in {'common_uncompressed','common_compact'})
                repacking=repack_common(image,expanded_common,temporary,temporary3,mode)
                manifest['common_atlas_storage']=repacking
                manifest['track3']=str(track3.resolve())
                manifest['track3_changed_sectors']=manifest.get('track3_changed_sectors',0)+repacking['root_directory_sectors']
            temporary.replace(output)
            if lossless or expanded_common:
                temporary3.replace(track3)
        finally:
            temporary.unlink(missing_ok=True)
            temporary3.unlink(missing_ok=True)
        cue = output.with_suffix(".cue")
        write_cue(image, output.resolve(), cue, track3_override=track3 if lossless or expanded_common else None)

    manifest["patched_sectors"] = sectors
    manifest["track"] = str(output.resolve())
    (output.parent / "text_build.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep the all-text export complete when a native disc build finishes.
    Project(ROOT, disc).export_text(data_dir / "text_export.csv")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    parser.add_argument("--out", type=Path, default=ROOT / "work" / "poc" / "Track5_KR.bin")
    args = parser.parse_args()
    result = build(args.disc, args.out)
    print(f"Built {len(result['cards'])} CPRO cards; patched {result['patched_sectors']} sectors")
    print(args.out.with_suffix(".cue"))


if __name__ == "__main__":
    main()
