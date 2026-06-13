# 学习文件看板

把本地 Markdown 错题本和复习计划生成成一个 GitHub Pages 静态复习看板。

唯一访问网址：

```text
https://hkh-seu.github.io/study-dashboard/
```

## 每天怎么用

1. 修改桌面上的 Markdown 文件。
2. 运行 `一键准备云端发布.py`。
3. 打开 GitHub Desktop。
4. Summary 填脚本给出的提交信息，例如 `Update study notes 2026-06-14 01:30`。
5. 点击 `Commit to main`。
6. 点击 `Push origin`。
7. 等 GitHub Actions 变成绿色。
8. 手机刷新 GitHub Pages 网址。

## 手机端体验

- 默认进入“今日复习计划”，不再单独维护首页。
- 底部导航只负责切换：计划、数学、专业。
- 左下角三横线打开当前页目录。
- 在计划页打开目录，只显示今日复习计划里的题目。
- 在数学页打开目录，只显示数学错题。
- 在专业页打开目录，只显示专业课错题。
- 点击目录里的分组只展开或收起，点击错题才跳转。
- 点击图片可以打开原图。

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
```

## 部署方式

项目使用 GitHub Pages 单站点模式。`.github/workflows/pages.yml` 会把 `cloud_site` 发布到 GitHub Pages。

需要确认：

1. GitHub 仓库是 Public。
2. `Settings -> Pages` 使用 GitHub Actions。
3. `Actions` 中的 `Deploy study dashboard to GitHub Pages` 是绿色成功状态。

## 隐私提醒

仓库公开后，`cloud_site` 中的错题本、复习计划和截图都会公开。不要把 token、账号、密码或其他隐私内容写进学习文件。
