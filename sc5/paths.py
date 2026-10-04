"""Keep writable project files outside a frozen executable's extraction folder."""
import os
from pathlib import Path
import sys


def project_root():
    configured = os.environ.get("SC5_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative):
    project = project_root() / relative
    if project.is_file():
        return project
    return Path(getattr(sys, "_MEIPASS", project_root())) / relative
