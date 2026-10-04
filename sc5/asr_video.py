"""Draft speech timing for multiplexed SFD cutscenes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel

from .asr import decode_audio
from .cli import DEFAULT_DATA, DEFAULT_DISC
from .disc import GDImage


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    p.add_argument("--output", type=Path, default=DEFAULT_DATA / "asr" / "videos.jsonl")
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.output.exists():
        done = {json.loads(line)["id"] for line in args.output.read_text(encoding="utf-8").splitlines()}
    model = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
    with GDImage(args.disc) as disc, args.output.open("a", encoding="utf-8", newline="\n") as out:
        for entry in disc.entries():
            if entry.suffix != ".SFD" or entry.name in done:
                continue
            try:
                audio = decode_audio(disc.read(entry.lba, entry.size))
                segments, _ = model.transcribe(audio, language="ja", beam_size=3,
                                               vad_filter=True, condition_on_previous_text=False)
                record = {"id": entry.name, "duration": round(len(audio) / 16000, 3),
                          "segments": [{"start": round(s.start, 3), "end": round(s.end, 3),
                                        "japanese": s.text.strip(), "korean": "",
                                        "status": "asr_draft"} for s in segments],
                          "status": "needs_listening"}
            except Exception as exc:
                record = {"id": entry.name, "segments": [], "status": "decode_error",
                          "error": str(exc)}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(entry.name, record["status"], len(record["segments"]), flush=True)


if __name__ == "__main__":
    main()
