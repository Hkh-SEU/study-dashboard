from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"
PYTHON_EXE = Path("D:/Python3_13/python.exe")

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ALLOWED_ADD_PATHS = [
    "publish.py",
    "config.json",
    "README.md",
    "cloud_site",
    ".github/workflows/pages.yml",
    "auto_update_site.py",
    "一键准备云端发布.py",
    "一键运行学习看板.py",
    "run.py",
    "setup_vendor.py",
]


class PushFailedError(RuntimeError):
    """Raised when terminal git push fails after a local commit was created."""


def python_command() -> str:
    if PYTHON_EXE.exists():
        return str(PYTHON_EXE)
    return sys.executable


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def auto_publish_config() -> tuple[bool, bool]:
    raw = load_config().get("auto_publish", {})
    if not isinstance(raw, dict):
        return True, True
    return bool(raw.get("enabled", True)), bool(raw.get("git_push", True))


def run_command(
    command: list[str],
    *,
    check: bool = True,
    verbose: bool = False,
) -> subprocess.CompletedProcess[str]:
    if verbose:
        print(f"> {' '.join(command)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        command,
        cwd=PROJECT_DIR,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
    )


def print_command_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip())


def open_github_desktop() -> bool:
    repo_path = quote(str(PROJECT_DIR).replace("\\", "/"), safe="/:")
    desktop_uris = [
        f"github-windows://openRepo/{repo_path}",
        f"x-github-client://openRepo/{repo_path}",
    ]
    for uri in desktop_uris:
        try:
            if hasattr(os, "startfile"):
                os.startfile(uri)  # type: ignore[attr-defined]
                return True
        except OSError:
            continue

    try:
        subprocess.Popen(["explorer", str(PROJECT_DIR)])
    except OSError:
        return False
    return False


def ensure_git_repo(verbose: bool) -> None:
    result = run_command(["git", "rev-parse", "--show-toplevel"], check=False, verbose=verbose)
    if result.returncode != 0:
        print_command_output(result)
        raise RuntimeError("study-dashboard is not a Git repository.")
    root = Path(result.stdout.strip()).resolve()
    if root != PROJECT_DIR.resolve():
        raise RuntimeError(f"Unexpected Git root: {root}")


def changed_dashboard_files(verbose: bool) -> list[str]:
    result = run_command(["git", "status", "--porcelain", "--", *ALLOWED_ADD_PATHS], check=True, verbose=verbose)
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        files.append(path)
    return files


def has_unmerged_paths(verbose: bool) -> bool:
    result = run_command(["git", "status", "--porcelain"], check=True, verbose=verbose)
    for line in result.stdout.splitlines():
        status = line[:2]
        if "U" in status or status in {"AA", "DD"}:
            return True
    return False


def git_add_allowed(dry_run: bool, verbose: bool) -> None:
    command = ["git", "add", "--", *ALLOWED_ADD_PATHS]
    if dry_run:
        if verbose:
            print(f"[dry-run] {' '.join(command)}")
        return
    result = run_command(command, check=False, verbose=verbose)
    if verbose:
        print_command_output(result)
    if result.returncode != 0:
        print_command_output(result)
        raise RuntimeError("git add failed. Please check file permissions or Git status.")


def git_commit(message: str, dry_run: bool, verbose: bool) -> bool:
    command = ["git", "commit", "-m", message]
    if dry_run:
        if verbose:
            print(f"[dry-run] {' '.join(command)}")
        return True
    result = run_command(command, check=False, verbose=verbose)
    if verbose:
        print_command_output(result)
    if result.returncode == 0:
        first_line = next((line for line in result.stdout.splitlines() if line.strip()), "")
        if first_line:
            print(f"  Commit: {first_line}")
        return True
    if "nothing to commit" in (result.stdout + result.stderr).lower():
        print("No commit created because there is nothing to commit.")
        return False
    print_command_output(result)
    raise RuntimeError("git commit failed. Please check Git status and try again.")


def git_push(dry_run: bool, verbose: bool) -> None:
    command = ["git", "push"]
    if dry_run:
        if verbose:
            print(f"[dry-run] {' '.join(command)}")
        return
    result = run_command(command, check=False, verbose=verbose)
    if verbose:
        print_command_output(result)
    if result.returncode != 0:
        raise PushFailedError("terminal git push failed")


def publish_site(verbose: bool) -> None:
    py = python_command()
    steps = [
        ("生成网页", ["publish.py", "--clean"]),
        ("检查部署文件", ["publish.py", "--deploy-check"]),
    ]
    for label, args in steps:
        result = run_command([py, *args], check=False, verbose=verbose)
        if verbose:
            print_command_output(result)
        if result.returncode != 0:
            print_command_output(result)
            raise RuntimeError(f"{' '.join(args)} failed.")
        print(f"✓ {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate, commit, and optionally push the study dashboard.")
    parser.add_argument("--dry-run", action="store_true", help="Show git actions without committing or pushing.")
    parser.add_argument("--no-push", action="store_true", help="Commit changes but skip git push.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed command output.")
    args = parser.parse_args()

    try:
        enabled, git_push_enabled = auto_publish_config()
        print("")
        print("Study Dashboard Auto Update")
        print("")
        publish_site(args.verbose)

        if not enabled:
            print("")
            print("auto_publish.enabled=false, so only cloud_site was generated.")
            return 0

        ensure_git_repo(args.verbose)
        if has_unmerged_paths(args.verbose):
            raise RuntimeError("Git has unresolved conflicts. Resolve them before auto publishing.")

        changed = changed_dashboard_files(args.verbose)
        if not changed:
            print("")
            print("网页内容没有变化，无需提交。")
            return 0

        print("")
        print(f"✓ 检测到网页变更：{len(changed)} 个文件")
        if args.verbose:
            for path in changed:
                print(f"  - {path}")

        message = f"Update study notes {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        git_add_allowed(args.dry_run, args.verbose)
        print("✓ 已加入 Git 暂存区" if not args.dry_run else "✓ 已模拟 Git 暂存")
        committed = git_commit(message, args.dry_run, args.verbose)
        if not committed:
            return 0
        print("✓ 已提交 commit" if not args.dry_run else f"✓ 已模拟 commit：{message}")

        should_push = git_push_enabled and not args.no_push
        if should_push:
            try:
                git_push(args.dry_run, args.verbose)
            except PushFailedError:
                print("")
                print("终端 git push 连接 GitHub 失败。")
                print("本地网页已经生成，commit 也已经完成，没有丢失。")
                opened = open_github_desktop()
                if opened:
                    print("已尝试打开 GitHub Desktop，请点击 Push origin 完成上传。")
                    print("如果 GitHub Desktop 没有弹出，请手动打开它并选择 study-dashboard。")
                    return 0
                print("请手动打开 GitHub Desktop，选择 study-dashboard，然后点击 Push origin。")
                return 1
            print("✓ 已推送到 GitHub" if not args.dry_run else "✓ 已模拟 push")
            print("")
            if args.dry_run:
                print("[dry-run] 已完成生成和检查；这里只是模拟 commit/push，没有真正提交或推送。")
            else:
                print("完成：网页已更新，GitHub Pages 正在部署。")
                print("手机稍等 30-90 秒后刷新：")
            print("https://hkh-seu.github.io/study-dashboard/")
        else:
            print("")
            if args.dry_run:
                print("[dry-run] 已完成生成和检查；这里只是模拟 commit，没有真正提交。")
            else:
                print("已生成网页并提交 commit。")
                print("auto_publish.git_push=false 或传入了 --no-push，因此没有执行 git push。")

        return 0
    except Exception as exc:  # noqa: BLE001
        print("")
        print(f"Auto update failed: {exc}")
        print("可以检查 GitHub Desktop 登录状态、网络连接，或手动使用 GitHub Desktop commit/push。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
