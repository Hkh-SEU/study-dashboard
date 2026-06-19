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

网页会自动检查新版本：

- 页面加载后立即检查一次。
- 前 5 分钟每 10 秒检查一次。
- 5 分钟后每 60 秒检查一次。
- 手机从后台、锁屏或其他 App 回到浏览器时，会立即检查一次。
- 发现新版本后会显示“内容已更新，正在刷新...”，然后自动刷新。
- 自动刷新时会在网址中带上 `?v=版本时间戳`，并让 docsify 请求 `plan.md`、`math.md`、`major.md`、`_sidebar.md` 时也带上版本参数，减少手机端继续读取旧 Markdown 缓存的概率。

GitHub Pages 部署完成后，手机通常会在 10-90 秒内看到新内容。如果仍然没有更新，可以手动刷新浏览器，或关闭当前标签页后重新打开。

## 桌面 Markdown 是唯一源文件

现在项目只把桌面 Markdown 当作正式源文件：

```text
C:/Desktop/错题本—数学.md
C:/Desktop/错题本—专业课.md
C:/Desktop/今日复习计划.md
```

Notebook 文件夹不再维护错题本或复习计划 Markdown 副本。你可以直接在桌面 Markdown 中修改文字、备注和图片引用；刷新网页时，发布器只读取这些桌面文件并生成 `cloud_site`，不会反向覆盖桌面 Markdown。

备注图片建议放在：

```text
C:/Desktop/SEU/错题截图—数学/备注/
C:/Desktop/SEU/错题截图—专业课/备注/
```

这两个 `备注` 文件夹不会被 controller 当作新错题截图扫描，也不会被移动或删除。新错题截图仍然放在：

```text
C:/Desktop/SEU/错题截图—数学
C:/Desktop/SEU/错题截图—专业课
```

处理后的正式错题截图会进入 `study_tools/error_correction/archive`。

## 正式学习前重置

如果要清空测试错题、从正式学习重新开始，可以使用仓库根目录下的重置脚本：

```powershell
D:\Python3_13\python.exe study_tools/reset_study_notes.py --check
```

`--check` 只预览，不修改文件。确认无误后，再由你手动运行：

```powershell
D:\Python3_13\python.exe study_tools/reset_study_notes.py --yes
```

`--yes` 会先备份，再重置三个桌面 Markdown 为干净模板，并把当前截图输入目录里的待处理截图移动到备份目录。它不会删除：

- `C:/Desktop/SEU/错题截图—数学/备注/`
- `C:/Desktop/SEU/错题截图—专业课/备注/`
- `study_tools/error_correction/archive`

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
