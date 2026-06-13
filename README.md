# 学习文件看板

这是一个极简的 GitHub Pages 学习复习看板。它把本地 Markdown 错题本和复习计划生成到 `cloud_site`，再通过 GitHub Pages 发布成手机可以访问的网页。

唯一访问网址：

```text
https://hkh-seu.github.io/study-dashboard/
```

## 每天怎么用

1. 修改桌面上的 Markdown 学习文件。
2. 运行：

```text
一键准备云端发布.py
```

3. 打开 GitHub Desktop。
4. Summary 填脚本给出的提交信息，例如：

```text
Update study notes 2026-06-13 16:30
```

5. 点击 `Commit to main`。
6. 点击 `Push origin`。
7. 等 GitHub Actions 自动部署完成。
8. 手机刷新：

```text
https://hkh-seu.github.io/study-dashboard/
```

如果手机看到旧内容，等一分钟再刷新。

## 手机端体验

- 底部导航用于快速切换：首页、计划、数学、专业课。
- 左侧目录用于快速跳转错题日期和错题编号。
- 错题图片可以点击打开原图，方便放大查看。
- 页面只保留复习相关信息，弱化文件状态和发布说明。

## 本地预览

直接运行：

```text
一键运行学习看板.py
```

或者运行：

```powershell
D:\Python3_13\python.exe run.py
```

本地预览只用于电脑端检查排版，公网访问以 GitHub Pages 为准。

## 命令速查

完整自检：

```powershell
D:\Python3_13\python.exe publish.py --doctor
```

重新生成静态站点：

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

## 配置

`config.json` 里的 `deploy` 保持 GitHub Pages 单站点模式：

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

不要在配置中写 token、账号或密码。

## GitHub Pages

项目通过 `.github/workflows/pages.yml` 把 `cloud_site` 发布到 GitHub Pages。

需要确认：

1. GitHub 仓库是 Public。
2. `Settings -> Pages` 使用 GitHub Actions。
3. `Actions` 中的 `Deploy study dashboard to GitHub Pages` 是绿色成功状态。

## 隐私提醒

仓库公开后，`cloud_site` 中的错题本、复习计划和截图也会公开。不要把 token、账号、密码或其他隐私内容写进学习文件或项目文件。
