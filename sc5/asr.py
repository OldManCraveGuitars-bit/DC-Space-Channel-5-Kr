"""Checkpointed Japanese speech draft extraction from every AFS voice slot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from faster_whisper import WhisperModel

from .assets import afs_members
from .cli import DEFAULT_DATA, DEFAULT_DISC, find_entry
from .disc import GDImage
from .media_decode import decode_audio


def run(disc: Path, archive: str, output: Path, model_name: str, limit: int | None, cpu_threads: int = 4):
    output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True,
                         cpu_threads=cpu_threads, num_workers=1)
    with GDImage(disc) as image:
        entry = find_entry(image, archive)
        blob = image.read(entry.lba, entry.size)
        members = afs_members(blob, archive)
        count = 0
        with output.open("a", encoding="utf-8", newline="\n") as stream:
            for item in members:
                if item["id"] in done or item["kind"] != "ADX":
                    continue
                if limit is not None and count >= limit:
                    break
                raw = blob[item["offset"]:item["offset"] + item["size"]]
                try:
                    audio = decode_audio(raw)
                    segments, _ = model.transcribe(audio, language="ja", beam_size=3,
                                                   vad_filter=True, condition_on_previous_text=False)
                    lines = [{"start": round(s.start, 3), "end": round(s.end, 3),
                              "japanese": s.text.strip(), "korean": "",
                              "status": "asr_draft"} for s in segments]
                    record = {"id": item["id"], "archive": archive,
                              "index": item["index"], "duration": round(len(audio) / 16000, 3),
                              "segments": lines, "status": "needs_listening"}
                except Exception as exc:
                    record = {"id": item["id"], "archive": archive,
                              "index": item["index"], "segments": [],
                              "status": "decode_error", "error": str(exc)}
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                count += 1
                print(f"{item['id']} {record['status']} {len(record['segments'])}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    parser.add_argument("--archive", default="VOICEDATA.AFS")
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA / "asr" / "VOICEDATA.jsonl")
    parser.add_argument("--model", default="small")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--cpu-threads", type=int, default=4)
    args = parser.parse_args()
    run(args.disc, args.archive, args.output, args.model, args.limit, args.cpu_threads)


if __name__ == "__main__":
    main()
