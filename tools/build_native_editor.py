"""Build one Windows executable with its font, Tk and media decoder bundled."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--console", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "SC5KoreanWorkbench.exe")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "work/native-build")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    stage = build / "release"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--noupx",
               "--name", "SC5KoreanWorkbench", "--distpath", str(stage),
               "--workpath", str(build / "objects"), "--specpath", str(build),
               "--paths", str(ROOT), "--collect-all", "av", "--collect-data", "imageio_ffmpeg",
               "--add-data", str(ROOT / "assets/fonts/yeongdeok-blueroad/Yeongdeok-Blueroad.ttf") + ";assets/fonts/yeongdeok-blueroad",
               "--add-data", str(ROOT / "native/subtitles.c") + ";native",
               "--add-data", str(ROOT / "native/judgment.c") + ";native",
               "--add-data", str(ROOT / "native/judgment_vmu.c") + ";native",
               "--add-data", str(ROOT / "native/hud.c") + ";native",
               "--add-data", str(ROOT / "native/link.ld") + ";native",
               "--add-data", str(ROOT / "native/sector_retime.dll") + ";native",
               "--console" if args.console else "--windowed"]
    for package in ("faster_whisper", "torch", "torchvision", "tensorflow", "matplotlib", "pandas", "IPython", "pytest", "scipy", "numba", "sympy"):
        command += ["--exclude-module", package]
    command += [str(ROOT / "tools/native_entry.py")]
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    exe = args.out.resolve()
    exe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage / "SC5KoreanWorkbench.exe", exe)
    manifest = {"executable": str(exe), "size": exe.stat().st_size,
                "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                "console": args.console, "font": "Yeongdeok Blueroad",
                "format": "Windows native Tk, single executable", "python_required_for_editor": False,
                "runtime_game_subtitles": "SH-4 ROM renderer, embedded glyphs/cues, CHD/GDI packaging, unmodified official player"}
    (ROOT / "work/native-editor-build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(exe)


if __name__ == "__main__":
    main()
