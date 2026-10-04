"""Launch an unmodified official player with the ROM-contained subtitles."""
from pathlib import Path
import json
import os
import shutil
import subprocess


def prepare_player(project):
    source = project.root / "work/native-rom/stock-flycast-2.7/flycast.exe"
    rom = project.root / "output/Space Channel 5 Korean Native.chd"
    if not source.is_file():
        raise ValueError("공식 Flycast 2.7 실행 파일이 없습니다.")
    if not rom.is_file():
        raise ValueError("먼저 ‘자막 내장 ROM 생성’을 실행하세요.")
    folder = project.root / "work/runtime/player-native"
    folder.mkdir(parents=True, exist_ok=True)
    player = folder / "flycast.exe"
    if not player.exists(): shutil.copyfile(source, player)
    data = folder / "data"
    data.mkdir(exist_ok=True)
    firmware = project.root / "work/firmware/dreamcast-user-20261004"
    for name in ("dc_boot.bin", "dc_flash.bin"):
        if not (data / name).exists(): shutil.copyfile(firmware / name, data / name)
    saves = project.root / "work/runtime/emucap/flycast/47841/portable/data"
    for save in saves.glob("*vmu*.bin"):
        if not (data / save.name).exists(): shutil.copyfile(save, data / save.name)
    config = folder / "emu.cfg"
    if not config.exists():
        config.write_text("[config]\nbios.UseReios = no\nDreamcast.ContentPath = "+str(rom.parent)+"\n", "utf-8")
    env = {k:v for k,v in os.environ.items() if not k.startswith("EMUCAP_") and k != "SC5_RUNTIME_CONFIG"}
    report = json.loads((project.root / "work/native-rom/build/build-report.json").read_text("utf-8"))
    return [str(player), str(rom)], env, folder, {"cue_count": report["stats"]["cues"]}


def launch_player(project):
    command, env, folder, report = prepare_player(project)
    process = subprocess.Popen(command, cwd=str(folder), env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"pid": process.pid, "cue_count": report["cue_count"], "player": command[0]}
