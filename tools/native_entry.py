import json
from pathlib import Path
import sys
import traceback


def entry():
    try:
        from sc5.native_editor import main
        main()
    except Exception:
        detail = traceback.format_exc()
        if "--build-disc" in sys.argv or "--package-native-rom" in sys.argv or "--smoke-test" in sys.argv:
            root = Path(sys.executable).resolve().parent
            if "--project" in sys.argv:
                root = Path(sys.argv[sys.argv.index("--project") + 1]).resolve()
            output = root / "work/native-worker-error.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"error": detail}, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            import tkinter as tk
            from tkinter import messagebox
            window = tk.Tk(); window.withdraw()
            messagebox.showerror("편집기 실행 오류", detail, parent=window)
            window.destroy()
        raise SystemExit(1)

if __name__ == "__main__":
    entry()
