from __future__ import annotations

import sys
from datetime import datetime

from publish import enabled_backup_urls, load_config, main as publish_main, primary_public_url


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
    suggested_message = f"Update study notes {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    _, _, deploy = load_config()
    primary_url = primary_public_url(deploy)
    backups = enabled_backup_urls(deploy)

    print("")
    print("访问入口：")
    if primary_url:
        print(f"- 主站：{primary_url}")
    else:
        print("- 主站：未配置，请部署后填写 config.json 的 deploy.primary_url")

    if backups:
        for backup in backups:
            print(f"- 备用站：{backup.name}：{backup.url}")
    else:
        print("- 备用站：暂未配置；后续可以添加 GitHub Pages 或 Vercel。")

    print("")
    print("下一步请这样做：")
    print("1. 打开 GitHub Desktop")
    print("2. 确认仓库是 study-dashboard")
    print(f"3. Summary 填：{suggested_message}")
    print("4. 点击 Commit to main")
    print("5. 点击 Push origin")
    print("6. 等云平台自动部署")
    print("7. 手机优先刷新主站；如果主站打不开，再试备用站")
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
