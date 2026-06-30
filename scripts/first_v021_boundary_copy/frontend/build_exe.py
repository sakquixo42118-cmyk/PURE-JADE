"""
PURE-JADE 前端 EXE 构建脚本

使用方法：
    pip install pyinstaller
    python build_exe.py

产物：dist/PURE-JADE.exe（约 25-35 MB，单文件）
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 确保 PyInstaller 可用
try:
    import PyInstaller
except ImportError:
    print("请先安装 PyInstaller:  pip install pyinstaller")
    sys.exit(1)

# ── 项目路径 ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
APP_SCRIPT = ROOT / "app.py"
DIST_DIR = ROOT / "dist"
WORK_DIR = ROOT / "build"

# ── 清理旧构建 ────────────────────────────────────────────────────────
for d in [DIST_DIR, WORK_DIR]:
    if d.exists():
        shutil.rmtree(d)

# ── 后端 main.py 路径（供 EXE 启动子进程时引用） ────────────────────
BACKEND_PATH = ROOT.parent / "main.py"
if not BACKEND_PATH.exists():
    print(f"[警告] 找不到后端脚本: {BACKEND_PATH}")
    print("        EXE 启动后可能需要手动运行后端。")

# ── PyInstaller 命令 ──────────────────────────────────────────────────
# 注意：后端 main.py 依赖 Python 解释器来运行（子进程），
# 所以 EXE 不打包 main.py，只打包前端。
# 用户需要确保系统安装了 Python 及所需依赖。

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--onefile",
    "--windowed",  # 无控制台窗口
    "--name", "PURE-JADE",
    "--distpath", str(DIST_DIR),
    "--workpath", str(WORK_DIR),
    f"--add-data={BACKEND_PATH}:.",
    # ── hidden imports + collect-all（customtkinter 含 DLL / 子包） ──
    "--collect-all", "customtkinter",
    "--hidden-import", "customtkinter",
    "--hidden-import", "httpx",
    "--hidden-import", "h2",
    "--hidden-import", "sniffio",
    "--hidden-import", "PIL",
    # ── 图标（如果有） ──
    # "--icon", "icon.ico",
    str(APP_SCRIPT),
]

print("=" * 60)
print("构建 PURE-JADE 前端 EXE")
print("=" * 60)
print(f"源文件: {APP_SCRIPT}")
print(f"输出目录: {DIST_DIR}")
print()

os.chdir(str(ROOT))
result = subprocess.run(cmd, check=False).returncode

if result == 0:
    print()
    print("Build succeeded!")
    print(f"    EXE located at: {DIST_DIR / 'PURE-JADE.exe'}")
else:
    print()
    print("Build failed, check errors above.")
