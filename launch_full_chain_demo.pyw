"""Double-click launcher for the PURE-JADE full-chain GUI."""

from __future__ import annotations

import os
import runpy
import shutil
import subprocess
import sys
import traceback
import importlib.util
from pathlib import Path
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
APP = ROOT / "scripts" / "full_chain_frontend" / "app.py"
REQUIRED_IMPORTS = ("uvicorn", "fastapi", "httpx", "dotenv", "pydantic")


def has_required_imports() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_IMPORTS)


def candidate_interpreters() -> list[Path]:
    candidates: list[Path] = []
    for name in ("pythonw", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for raw in (
        r"G:\python\pythonw.exe",
        r"G:\python\python.exe",
        r"D:\python\pythonw.exe",
        r"D:\python\python.exe",
    ):
        candidates.append(Path(raw))

    current = Path(sys.executable).resolve()
    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or resolved == current or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    return result


def interpreter_has_required_imports(interpreter: Path) -> bool:
    code = "import importlib.util; missing=[m for m in %r if importlib.util.find_spec(m) is None]; raise SystemExit(1 if missing else 0)" % (
        REQUIRED_IMPORTS,
    )
    result = subprocess.run(
        [str(interpreter), "-c", code],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def relaunch_with_usable_python() -> bool:
    if has_required_imports():
        return False
    for interpreter in candidate_interpreters():
        if interpreter_has_required_imports(interpreter):
            subprocess.Popen([str(interpreter), str(Path(__file__).resolve())], cwd=ROOT)
            return True
    return False


def main() -> None:
    if relaunch_with_usable_python():
        return
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    runpy.run_path(str(APP), run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - GUI launcher should show startup failures.
        messagebox.showerror(
            "PURE-JADE 启动失败",
            f"{error}\n\n{traceback.format_exc(limit=5)}",
        )
