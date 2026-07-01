from pathlib import Path
import runpy
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
APP_PATH = PROJECT_ROOT / "scripts" / "ab_comparison" / "app.py"

sys.path.insert(0, str(PROJECT_ROOT))
runpy.run_path(str(APP_PATH), run_name="__main__")
