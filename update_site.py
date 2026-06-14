from __future__ import annotations

import sys
from pathlib import Path


sys.dont_write_bytecode = True

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from auto_update_site import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
