from __future__ import annotations

import sys

from publish import main as publish_main


def main() -> int:
    print("Study Dashboard cloud-ready run")
    print("Generating cloud_site and checking deployment files...")
    print("")

    original_argv = sys.argv[:]
    try:
        sys.argv = ["publish.py", "--cloud-ready"]
        return publish_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
