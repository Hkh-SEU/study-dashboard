# 学习文件看板

把本地 Markdown 错题本和复习计划生成成一个 GitHub Pages 静态复习看板。

唯一访问网址：

```text
https://hkh-seu.github.io/study-dashboard/
```

## 半自动发布

现在网页更新已经独立成单独入口：

- `一键更新网页.py`

三个 controller 只负责更新桌面 Markdown 文件：

- `Notebook/run_controller_数学.py`
- `Notebook/run_controller_专业课.py`
- `Notebook/run_controller_复习.py`

当你想更新网页时，运行 `一键更新网页.py`。它会自动执行：

1. 生成最新 `cloud_site`
2. 检查 GitHub Pages 部署文件
3. 自动提交 `study-dashboard` 相关文件
4. 自动打开 GitHub Desktop
5. 你点击 `Push origin`
6. 等 GitHub Actions 部署
7. 手机网页检测到新版本后自动刷新

自动提交信息形如：

```text
Update study notes 2026-06-14 16:30
```

## 半自动发布开关

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

网页每 60 秒检查一次 `version.json`。如果发现新版本，会显示：

```text
内容已更新，正在刷新...
```

然后自动刷新页面。手机端和电脑端都生效。如果手机没自动刷新，可以手动刷新一次。

## 手动发布

如果想完全手动，也可以运行：

```powershell
D:\Python3_13\python.exe publish.py --clean
D:\Python3_13\python.exe publish.py --deploy-check
```

然后打开 GitHub Desktop，手动 Commit + Push。

## GitHub Desktop 没有自动打开怎么办

常见原因：

- GitHub Desktop 没登录
- GitHub Desktop 没有关联 `study-dashboard`
- 系统没有注册 GitHub Desktop 的打开协议

处理建议：

1. 手动打开 GitHub Desktop。
2. 选择 `study-dashboard` 仓库。
3. 点击 `Push origin`。
4. 不要随便执行 `git reset --hard`。
5. 不要强推。

## 手机端体验

- 默认进入“今日复习计划”。
- 底部导航切换：计划、数学、专业。
- 左下角三横线打开当前页目录。
- 在计划页打开目录，只显示今日计划相关题目。
- 在数学页打开目录，只显示数学错题。
- 在专业页打开目录，只显示专业课错题。
- 点击目录里的分组只展开或收起，点击错题才跳转。
- 点击图片会在站内预览，点击关闭按钮或背景可关闭。

## 本地预览

```powershell
D:\Python3_13\python.exe run.py
```

也可以直接运行：

```text
一键运行学习看板.py
```

## 命令速查

```powershell
D:\Python3_13\python.exe publish.py --doctor
D:\Python3_13\python.exe publish.py --clean
D:\Python3_13\python.exe publish.py --deploy-check
D:\Python3_13\python.exe publish.py --open-public
D:\Python3_13\python.exe auto_update_site.py --dry-run
```

## 部署方式

项目使用 GitHub Pages 单站点模式。`.github/workflows/pages.yml` 会把 `cloud_site` 发布到 GitHub Pages。

需要确认：

1. GitHub 仓库是 Public。
2. `Settings -> Pages` 使用 GitHub Actions。
3. `Actions` 中的 `Deploy study dashboard to GitHub Pages` 是绿色成功状态。

## 隐私提醒

自动发布会把 `cloud_site` 中的错题本、复习计划和截图推送到 GitHub。仓库公开后，这些内容也会公开。不要把 token、账号、密码或其他隐私内容写进学习文件。
