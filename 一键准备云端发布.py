from __future__ import annotations

import sys

from publish import main as publish_main


def run_publish_command(*args: str) -> int:
    original_argv = sys.argv[:]
    try:
        sys.argv = ["publish.py", *args]
        return publish_main()
    finally:
        sys.argv = original_argv


def print_header() -> None:
    print("")
    print("学习看板：一键准备云端发布")
    print("=" * 34)
    print("这个脚本会检查源文件、生成 cloud_site、检查部署文件。")
    print("它不会自动 git push，也不会上传任何 token 或密码。")
    print("")


def print_next_steps() -> None:
    print("")
    print("下一步请这样做：")
    print("1. 打开 GitHub Desktop")
    print("2. 确认仓库是 study-dashboard")
    print("3. Summary 填：Update study notes")
    print("4. 点击 Commit to main")
    print("5. 点击 Push origin")
    print("6. 等 Cloudflare Pages 自动部署")
    print("7. 手机刷新：https://study-dashboard-pages.pages.dev")
    print("")
    print("如果手机看到旧内容，先等一分钟或强制刷新。")
    print("如果 pages.dev 打不开，通常是网络环境问题，不一定是项目失败。")


def main() -> int:
    print_header()

    steps = [
        ("检查配置和源 Markdown 文件", ("--doctor",)),
        ("生成手机端网页文件", ("--clean",)),
        ("检查云端部署文件", ("--deploy-check",)),
    ]

    for index, (title, args) in enumerate(steps, start=1):
        print("")
        print(f"[{index}/3] {title}")
        code = run_publish_command(*args)
        if code != 0:
            print("")
            print("已停止：上一步没有通过。请根据上面的提示修复后再运行。")
            return code

    print("")
    print("已检查源文件。")
    print("已生成网页。")
    print("已准备好发布。")
    print_next_steps()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
