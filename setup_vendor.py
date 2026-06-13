from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "cloud_site"

DOCSIFY_ASSETS = [
    (
        "vue.css",
        "https://cdn.jsdelivr.net/npm/docsify@4/lib/themes/vue.css",
    ),
    (
        "docsify.min.js",
        "https://cdn.jsdelivr.net/npm/docsify@4/lib/docsify.min.js",
    ),
    (
        "search.min.js",
        "https://cdn.jsdelivr.net/npm/docsify@4/lib/plugins/search.min.js",
    ),
]


def vendor_dir(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return output_dir / "assets" / "vendor" / "docsify"


def ensure_vendor_assets(output_dir: Path = DEFAULT_OUTPUT_DIR, force: bool = False) -> list[Path]:
    target_dir = vendor_dir(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, url in DOCSIFY_ASSETS:
        target = target_dir / filename
        if target.exists() and target.stat().st_size > 0 and not force:
            written.append(target)
            continue

        print(f"Downloading {filename}...")
        request = urllib.request.Request(url, headers={"User-Agent": "study-dashboard/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if not data:
            raise RuntimeError(f"Downloaded empty file: {url}")
        target.write_bytes(data)
        written.append(target)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Download docsify static assets into cloud_site.")
    parser.add_argument("--force", action="store_true", help="Redownload assets even if they already exist.")
    args = parser.parse_args()

    try:
        assets = ensure_vendor_assets(force=args.force)
    except Exception as exc:  # noqa: BLE001
        print(f"Vendor setup failed: {exc}")
        return 1

    print("Docsify vendor assets are ready:")
    for asset in assets:
        print(f"  {asset.relative_to(PROJECT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
