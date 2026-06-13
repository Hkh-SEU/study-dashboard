# 学习文件看板

这是一个 GitHub Pages 单站点模式的学习看板。它把本地桌面上的 Markdown 错题本和复习计划生成到 `cloud_site`，再通过 GitHub Pages 发布成手机可以访问的网页。

唯一访问网址：

```text
https://hkh-seu.github.io/study-dashboard/
```

## 每天怎么用

1. 修改桌面 Markdown 文件：

```text
C:/Desktop/错题本—数学.md
C:/Desktop/错题本—专业课.md
C:/Desktop/今日复习计划.md
```

2. 运行：

```text
一键准备云端发布.py
```

3. 打开 GitHub Desktop。

4. Summary 填脚本给出的建议提交信息，例如：

```text
Update study notes 2026-06-13 16:30
```

5. 点击 `Commit to main`。

6. 点击 `Push origin`。

7. 等 GitHub Actions 自动部署。

8. 手机刷新：

```text
https://hkh-seu.github.io/study-dashboard/
```

如果手机看到旧内容，先等一分钟或强制刷新。

## 本地预览

可以直接运行：

```text
一键运行学习看板.py
```

也可以运行：

```powershell
D:\Python3_13\python.exe run.py
```

本地预览只用于电脑上检查排版，公网访问以 GitHub Pages 为准。

## 命令速查

完整自检：

```powershell
D:\Python3_13\python.exe publish.py --doctor
```

生成静态站点：

```powershell
D:\Python3_13\python.exe publish.py --clean
```

部署文件检查：

```powershell
D:\Python3_13\python.exe publish.py --deploy-check
```

打开公网网址：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

## 配置说明

`config.json` 中的 `deploy` 只保留 GitHub Pages：

```json
{
  "deploy": {
    "provider": "github_pages",
    "public_url": "https://hkh-seu.github.io/study-dashboard/",
    "root_directory": "",
    "output_directory": "cloud_site",
    "git_enabled": false,
    "default_branch": "main"
  }
}
```

说明：

- `provider`：固定为 `github_pages`。
- `public_url`：唯一公网访问地址。
- `output_directory`：发布目录，保持 `cloud_site`。
- 不要在配置中写 token、账号或密码。

## GitHub Pages 部署

项目通过 `.github/workflows/pages.yml` 把 `cloud_site` 发布到 GitHub Pages。

需要确认：

1. GitHub 仓库是 Public。
2. `Settings -> Pages` 使用 GitHub Actions。
3. `Actions` 里的 `Deploy study dashboard to GitHub Pages` 是绿色成功状态。

## 隐私提醒

- `cloud_site` 会包含错题本、计划书和截图。
- 仓库公开后，这些内容也会公开。
- 不要把 token、账号、密码写进项目文件。

## 生成内容

`cloud_site` 包含：

```text
index.html
README.md
_sidebar.md
math.md
major.md
plan.md
assets/cloud.css
assets/vendor/docsify/
assets/media/
```
