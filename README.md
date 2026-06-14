# 学习文件看板

把桌面上的 Markdown 错题本和复习计划生成成一个 GitHub Pages 静态复习看板。

唯一访问网址：

```text
https://hkh-seu.github.io/study-dashboard/
```

## 目录结构

```text
study-dashboard
├── .github/workflows/pages.yml   # GitHub Pages 自动部署
├── cloud_site                    # 生成后的网站文件
├── auto_update_site.py           # 半自动更新：生成、commit、打开 GitHub Desktop
├── update_site.py                # 给桌宠/手动运行使用的简洁入口
├── publish.py                    # 核心发布器
├── run.py                        # 本地预览
├── setup_vendor.py               # docsify 本地资源准备
├── config.json                   # 文档路径和发布配置
└── README.md
```

## 日常使用

平时你只需要：

1. 运行 controller 更新桌面 Markdown 文件。
2. 在桌宠里点击 `刷新网页内容`，或运行：

```powershell
D:\Python3_13\python.exe update_site.py
```

3. GitHub Desktop 打开后，点击 `Push origin`。
4. 等 GitHub Actions 部署完成。
5. 手机刷新 GitHub Pages 网址。

`update_site.py` 会自动完成：

- 生成最新 `cloud_site`
- 检查 GitHub Pages 部署文件
- 自动 commit `study-dashboard` 相关文件
- 打开 GitHub Desktop，等待你手动点击 `Push origin`

## 本地预览

```powershell
D:\Python3_13\python.exe run.py
```

## 常用命令

```powershell
D:\Python3_13\python.exe publish.py --doctor
D:\Python3_13\python.exe publish.py --clean
D:\Python3_13\python.exe publish.py --deploy-check
D:\Python3_13\python.exe publish.py --open-public
D:\Python3_13\python.exe update_site.py --dry-run
```

## 自动发布开关

`config.json` 中有：

```json
"auto_publish": {
  "enabled": true,
  "git_push": false,
  "open_github_desktop": true
}
```

- `enabled=false`：只生成网页，不 commit。
- `git_push=false`：自动 commit，但不使用终端 push，推荐保持这个设置。
- `open_github_desktop=true`：commit 后自动尝试打开 GitHub Desktop。
- `git_push=true`：自动 commit 并尝试终端 push，不推荐作为日常方式。

半自动发布只会添加 `study-dashboard` 内的白名单文件，不会 `git add` 整个仓库，不会强推，不会 reset，也不会写入 token、账号或密码。

## 网页自动刷新

每次发布都会生成：

```text
cloud_site/version.json
```

网页前 3 分钟每 15 秒检查一次新版本，之后每 60 秒检查一次。发现新版本后会自动刷新。手机端和电脑端都生效。

## GitHub Pages

项目使用 GitHub Pages 单站点模式。`.github/workflows/pages.yml` 会把 `cloud_site` 发布到 GitHub Pages。

需要确认：

1. GitHub 仓库是 Public。
2. `Settings -> Pages` 使用 GitHub Actions。
3. `Actions` 中的 `Deploy study dashboard to GitHub Pages` 是绿色成功状态。

## 手机端体验

- 默认进入今日复习计划。
- 底部导航切换：计划、数学、专业。
- 左下角三横线打开当前页面目录。
- 在计划页打开目录，只显示今日计划相关题目。
- 在数学页打开目录，只显示数学错题。
- 在专业页打开目录，只显示专业课错题。
- 点击图片会在站内预览，点击关闭按钮或背景可关闭。

## 隐私提醒

`cloud_site` 中包含错题本、复习计划和截图。仓库公开后，这些内容也会公开。不要把 token、账号、密码或其他隐私内容写进学习文件。
