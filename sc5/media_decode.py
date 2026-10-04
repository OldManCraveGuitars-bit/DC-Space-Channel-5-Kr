"""Media decoding shared by the native editor and offline speech extraction."""
import subprocess
import numpy as np
import imageio_ffmpeg


def ffmpeg_run(arguments, **kwargs):
    return subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", *arguments],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def decode_audio(data):
    result = ffmpeg_run(["-i", "pipe:0", "-vn", "-ac", "1", "-ar", "16000",
                         "-f", "f32le", "pipe:1"], input=data)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace")[-1000:])
    return np.frombuffer(result.stdout, dtype="<f4").copy()
