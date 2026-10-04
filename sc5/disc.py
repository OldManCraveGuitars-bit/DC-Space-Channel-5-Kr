"""Read the original raw-sector Space Channel 5 GD-ROM without changing it.

The high-density ISO directory is on track 3. Its file extents continue on
track 5, with an audio track in between. A normal ISO reader misses that map.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import re

SECTOR = 2352
PAYLOAD = 2048
SYNC = bytes.fromhex("00ffffffffffffffffffff00")


@dataclass(frozen=True)
class FileEntry:
    name: str
    lba: int
    size: int
    flags: int

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.upper()


class GDImage:
    def __init__(self, cue_dir: Path, *, track3: Path | None = None, track5: Path | None = None):
        self.cue_dir = Path(cue_dir)
        self.track3 = Path(track3) if track3 else next(self.cue_dir.glob("*Track 3).bin"))
        self.track5 = Path(track5) if track5 else next(self.cue_dir.glob("*Track 5).bin"))
        self._files = {3: self.track3.open("rb"), 5: self.track5.open("rb")}
        self.track3_sectors = self.track3.stat().st_size // SECTOR
        self.track5_sectors = self.track5.stat().st_size // SECTOR
        pvd = self._sector(3, 16)
        if pvd[:7] != b"\x01CD001\x01":
            raise ValueError("Track 3 ISO9660 primary volume descriptor was not found")
        self.volume_start = 45000  # Dreamcast high-density area starts here.
        self.volume_blocks = int.from_bytes(pvd[80:84], "little")
        self.track5_start = self.volume_start + self.volume_blocks - self.track5_sectors
        if self.track5_start <= self.volume_start + self.track3_sectors:
            raise ValueError("Unexpected GD-ROM track layout")
        self.root_lba = int.from_bytes(pvd[158:162], "little")
        self.root_size = int.from_bytes(pvd[166:170], "little")

    def close(self):
        for f in self._files.values():
            f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _sector(self, track: int, index: int) -> bytes:
        f = self._files[track]
        f.seek(index * SECTOR)
        raw = f.read(SECTOR)
        if len(raw) != SECTOR or raw[:12] != SYNC or raw[15] != 1:
            raise ValueError(f"Invalid Mode 1 sector: track {track}, sector {index}")
        return raw[16:16 + PAYLOAD]

    def read(self, lba: int, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            if self.volume_start <= lba < self.volume_start + self.track3_sectors:
                track, index = 3, lba - self.volume_start
            elif self.track5_start <= lba < self.track5_start + self.track5_sectors:
                track, index = 5, lba - self.track5_start
            else:
                raise ValueError(f"LBA {lba} falls outside data tracks")
            result.extend(self._sector(track, index))
            lba += 1
        return bytes(result[:size])

    def entries(self) -> list[FileEntry]:
        data = self.read(self.root_lba, self.root_size)
        entries = []
        offset = 0
        while offset < len(data):
            length = data[offset]
            if length == 0:
                offset = ((offset // PAYLOAD) + 1) * PAYLOAD
                continue
            record = data[offset:offset + length]
            if len(record) != length or length < 34:
                raise ValueError(f"Broken ISO directory record at {offset}")
            raw_name = record[33:33 + record[32]]
            if raw_name not in (b"\x00", b"\x01"):
                name = re.sub(r";\d+$", "", raw_name.decode("ascii"))
                entries.append(FileEntry(name, int.from_bytes(record[2:6], "little"),
                                         int.from_bytes(record[10:14], "little"), record[25]))
            offset += length
        return entries

    def export(self, entry: FileEntry, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as out:
            remaining, lba = entry.size, entry.lba
            while remaining:
                chunk = self.read(lba, min(remaining, PAYLOAD * 64))
                out.write(chunk)
                remaining -= len(chunk)
                lba += (len(chunk) + PAYLOAD - 1) // PAYLOAD


def write_manifest(image: GDImage, output: Path):
    entries = image.entries()
    manifest = {
        "source": str(image.cue_dir),
        "tracks": {"track3": str(image.track3), "track5": str(image.track5)},
        "layout": {"volume_start_lba": image.volume_start,
                   "track5_start_lba": image.track5_start,
                   "volume_blocks": image.volume_blocks},
        "files": [asdict(e) | {"category": classify(e)} for e in entries],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def classify(entry: FileEntry) -> str:
    return {
        ".M1V": "video", ".SFD": "video", ".AFS": "audio_archive",
        ".PVR": "image", ".PVM": "image_archive", ".RB": "scene_data",
        ".BIN": "binary", ".MPB": "music", ".MSB": "music",
    }.get(entry.suffix, "other")
