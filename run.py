from __future__ import annotations

import sys

from publish import main as publish_main


def main() -> int:
    print("Study Dashboard one-click run")
    print("Step 1/2: checking and generating cloud_site...")
    print("")

    original_argv = sys.argv[:]
    try:
        sys.argv = ["publish.py", "--clean", "--preview"]
        return publish_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
