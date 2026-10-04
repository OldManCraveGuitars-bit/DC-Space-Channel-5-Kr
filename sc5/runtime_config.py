"""Export saved Korean cues for ROM compilation and the review preview."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from .editor_project import Project, read_json, timing_errors

JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
EXCLUDED = {"excluded", "english_keep", "no_change", "asr_hallucination"}


def media_key(kind, item_id):
    if kind == "videos":
        return "movie:" + item_id.lower()
    archive, member = item_id.rsplit(":", 1)
    return archive.upper() + ":" + str(int(member))


def export_runtime(project):
    """Only saved translations are eligible; untouched ASR is never exported."""
    old = read_json(project.root / "work/runtime/config.json", {})
    config = {"disc": "Space Channel 5 (Japan)", "font": str(project.font),
              "event_log": str(project.root / "work/runtime/voice-events.jsonl"),
              "afs_bases": {}, "clips": {}, "durations": {}, "dump_textures": False,
              "caption_style": "box", "caption_box_alpha": 115, "execution_engine": "jit",
              "caption_observer_enabled": False}
    # Preserve explicit diagnostic preferences and the chosen event log.
    for name in ("event_log", "dump_textures", "dump_unique_textures", "caption_style", "caption_box_alpha"):
        if name in old:
            config[name] = old[name]
    if config["caption_style"] not in ("outline", "box"):
        raise ValueError("자막 표시는 outline 또는 box여야 합니다.")
    alpha = config["caption_box_alpha"]
    if not isinstance(alpha, int) or not 0 <= alpha <= 255:
        raise ValueError("자막 배경 농도는 0~255 사이의 정수여야 합니다.")
    for entry in read_json(project.data / "disc.json", {}).get("files", []):
        if entry["name"].upper().endswith(".AFS"):
            config["afs_bases"][str(entry["lba"] + 150)] = entry["name"].upper()
    report = {"version": 1, "created": datetime.now(timezone.utc).isoformat(),
              "config": str(project.root / "work/runtime/config.json"),
              "clips": [], "skipped": [], "cue_count": 0}
    for kind in ("voices", "videos"):
        for item_id, edit in project.edits(kind).items():
            item = project.item(kind, item_id)
            eligible = []
            for index, segment in enumerate(edit.get("segments", [])):
                korean = segment.get("korean", "").strip()
                reason = None
                if edit.get("status") in EXCLUDED or segment.get("status") in EXCLUDED:
                    reason = "excluded"
                elif not korean:
                    reason = "untranslated"
                elif not JAPANESE.search(segment.get("japanese", "")):
                    reason = "Japanese source required; English is preserved"
                if reason:
                    report["skipped"].append({"kind": kind, "id": item_id, "segment": index, "reason": reason})
                    continue
                eligible.append(segment | {"korean": korean})
            if not eligible:
                continue
            duration = float(item.get("duration", 0))
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"{item_id}: 실제 재생 길이가 필요합니다.")
            errors = timing_errors(eligible, duration)
            if errors:
                raise ValueError(f"{item_id}: 번역 자막 시간 오류 {len(errors)}개")
            key = media_key(kind, item_id)
            cues = [{"start": float(s["start"]), "end": float(s["end"]),
                     "japanese": s["japanese"], "korean": s["korean"]} for s in eligible]
            for source, cue in zip(eligible, cues):
                if "bottom_offset" in source:
                    offset = float(source["bottom_offset"])
                    if not math.isfinite(offset) or not 0 <= offset <= 400:
                        raise ValueError(f"{item_id}: 자막 위치는 0~400 사이여야 합니다.")
                    cue["bottom_offset"] = offset
            cues.sort(key=lambda s: (s["start"], s["end"]))
            config["clips"][key] = cues
            config["durations"][key] = duration
            report["clips"].append({"kind": kind, "id": item_id, "key": key,
                                    "duration": duration, "cues": len(cues)})
            report["cue_count"] += len(cues)
    project._commit({project.root / "work/runtime/config.json":
                     (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                     project.root / "work/runtime/caption-export.json":
                     (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = export_runtime(Project(args.project))
    print(json.dumps({"config": result["config"], "clips": len(result["clips"]),
                      "cue_count": result["cue_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
