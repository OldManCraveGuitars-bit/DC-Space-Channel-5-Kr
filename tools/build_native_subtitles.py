"""Compile and embed the ROM-contained Dreamcast subtitle renderer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sc5.native_subtitles import main
if __name__ == "__main__": main()
