# 学习文件看板

这是一个 Markdown 静态站点发布器。它把本地桌面上的错题本和复习计划生成到 `cloud_site`，再发布到公网静态托管平台，方便手机和平板访问。

当前访问结构很简单：

- 主站：Cloudflare Pages
- 备用站：GitHub Pages

备用站不会自动跳转。主站打不开时，手动打开 GitHub Pages 备用网址。

## 为什么只保留一个备用站

- 项目很小，只是个人学习复习看板。
- 一个 GitHub Pages 备用入口已经够用。
- 平台越多，维护越麻烦。
- GitHub Pages 和 GitHub 仓库天然配合，适合作为备用入口。

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
Update study notes 2026-06-13 14:20
```

5. 点击 `Commit to main`。

6. 点击 `Push origin`。

7. 等云平台自动部署。

8. 手机优先打开 Cloudflare Pages 主站；如果主站打不开，再打开 GitHub Pages 备用站。

## 命令速查

本地预览：

```powershell
D:\Python3_13\python.exe run.py
```

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

打开主站：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

打开 GitHub Pages 备用站：

```powershell
D:\Python3_13\python.exe publish.py --open-backup
```

打开主站和备用站：

```powershell
D:\Python3_13\python.exe publish.py --open-all
```

## 配置说明

`config.json` 中的 `deploy` 只保留一个备用站：

```json
{
  "deploy": {
    "provider": "cloudflare_pages",
    "primary_url": "https://study-dashboard-pages.pages.dev",
    "public_url": "https://study-dashboard-pages.pages.dev",
    "backup_urls": [
      {
        "name": "GitHub Pages",
        "url": "",
        "enabled": false
      }
    ],
    "root_directory": "",
    "output_directory": "cloud_site",
    "git_enabled": false,
    "default_branch": "main"
  }
}
```

说明：

- `primary_url`：Cloudflare Pages 主站。
- `public_url`：旧字段，保留兼容；如果 `primary_url` 为空，脚本会 fallback 到它。
- `backup_urls[0]`：GitHub Pages 备用站。
- `output_directory`：云平台发布目录，保持 `cloud_site`。
- 不要在配置中写 token、账号或密码。

## GitHub Pages 备用站配置

因为静态站点生成在 `cloud_site`，GitHub Pages 的普通 branch 方式通常不能直接选择这个目录。更稳的方式是使用 GitHub Actions 发布 `cloud_site`。

推荐步骤：

1. 打开 GitHub 仓库 `study-dashboard`。
2. 进入 `Settings`。
3. 找到 `Pages`。
4. Source 选择 `GitHub Actions`。
5. 确认项目里已经有 `.github/workflows/pages.yml`。
6. 用 GitHub Desktop 提交并 Push。
7. GitHub Actions 跑完后，会生成类似下面的网址：

```text
https://Hkh-SEU.github.io/study-dashboard/
```

8. 把这个网址填入 `config.json`：

```json
{
  "name": "GitHub Pages",
  "url": "https://Hkh-SEU.github.io/study-dashboard/",
  "enabled": true
}
```

之后主站打不开时，就手动打开 GitHub Pages 备用站。

## 隐私提醒

- `cloud_site` 会包含错题本、计划书和截图。
- GitHub Pages 通常适合公开内容。
- 如果仓库公开，错题本和截图也会公开。
- 如果资料私密，不建议公开 GitHub Pages。
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

其中 `assets/media/` 是从 Markdown 图片引用中复制出来的错题截图资源。
