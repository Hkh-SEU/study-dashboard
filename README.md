# 学习文件看板

这是一个 Markdown 静态站点发布器。它把本地桌面上的 Markdown 错题本和复习计划生成到 `cloud_site`，再部署到 Cloudflare Pages、GitHub Pages 或 Vercel 后，手机和平板就能在不同网络下通过独立网址访问。

它不是公网服务器，也不会把本地端口暴露到公网。真正跨网络访问依赖静态托管平台。

## 两种用途

本地预览：

- 运行 `一键运行学习看板.py`
- 自动生成 `cloud_site`
- 启动本地预览
- 电脑浏览器打开 `http://127.0.0.1:8080/#/`

云端发布准备：

- 运行 `一键准备云端发布.py`
- 自动生成 `cloud_site`
- 检查部署文件是否齐全
- 打印 Cloudflare Pages / GitHub Pages / Vercel 部署设置
- 不会自动 git push

## 为什么本地预览不能跨网络访问

- `127.0.0.1` 只代表当前电脑，手机访问自己的 `127.0.0.1` 不会访问到电脑。
- 局域网 IP 只适合同一个 Wi-Fi。
- 不建议把本地电脑端口直接暴露到公网。

如果手机和平板要在不同网络下访问，需要把 `cloud_site` 部署到公网静态托管平台，例如 Cloudflare Pages、GitHub Pages 或 Vercel。

## 日常流程

1. 更新桌面 Markdown：

```text
C:/Desktop/错题本—数学.md
C:/Desktop/错题本—专业课.md
C:/Desktop/今日复习计划.md
```

2. 本地预览：

```text
打开 一键运行学习看板.py，然后点击 VS Code 右上角运行按钮
```

3. 准备云端发布：

```text
打开 一键准备云端发布.py，然后点击 VS Code 右上角运行按钮
```

4. 手动提交并推送到 GitHub，或使用带确认的命令：

```powershell
D:\Python3_13\python.exe publish.py --cloud-ready --git
```

5. 等云平台自动部署。

6. 手机打开部署平台给出的独立网址，例如：

```text
https://study-dashboard-pages.pages.dev
```

## 命令速查

本地预览：

```powershell
D:\Python3_13\python.exe run.py
```

检查源文件：

```powershell
D:\Python3_13\python.exe publish.py --check
```

生成静态站点：

```powershell
D:\Python3_13\python.exe publish.py --clean
```

部署文件检查：

```powershell
D:\Python3_13\python.exe publish.py --deploy-check
```

生成并检查云端发布文件：

```powershell
D:\Python3_13\python.exe publish.py --cloud-ready
```

打开公网网址：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

当前 `deploy.public_url` 已填写为 Cloudflare Pages 地址；如果以后换平台或绑定域名，再改成新的网址。

带确认的 git 发布：

```powershell
D:\Python3_13\python.exe publish.py --cloud-ready --git --message "Update study dashboard"
```

## 配置说明

`config.json` 中的 `deploy` 用于记录云端部署信息：

```json
{
  "deploy": {
    "provider": "cloudflare_pages",
    "public_url": "https://study-dashboard-pages.pages.dev",
    "root_directory": "",
    "output_directory": "cloud_site",
    "git_enabled": false,
    "default_branch": "main"
  }
}
```

说明：

- `public_url`：部署成功后的真实网址，例如 `https://study-dashboard-pages.pages.dev`
- `root_directory`：项目在 GitHub 仓库中的目录；如果仓库根目录就是 `study-dashboard`，保持空字符串
- `output_directory`：云平台要发布的目录，保持 `cloud_site`
- 不要在配置中写 token、账号或密码

## Cloudflare Pages

推荐 Cloudflare Pages，后续可以配 Cloudflare Access 做访问保护。

设置方式：

```text
Root directory: 留空
Build command: 留空
Build output directory: cloud_site
```

如果以后把项目放进大仓库的子目录，再把 Root directory 改成类似 `study_tools/study-dashboard`。

部署完成后，Cloudflare 会给出 `pages.dev` 网址。把它填入 `config.json`：

```json
"public_url": "https://你的项目名.pages.dev"
```

之后可以运行：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

## GitHub Pages

GitHub Pages 适合公开内容。它可以托管 `cloud_site`，但如果错题本、计划书或截图包含隐私信息，不建议用公开 GitHub Pages。

## Vercel

Vercel 也可以托管静态站点。连接 GitHub 仓库后，将输出目录设置为：

```text
cloud_site
```

## 隐私提醒

- `cloud_site` 会包含错题本、计划书和截图。
- 公开仓库或公开 Pages 会公开这些资料。
- 私密内容建议使用：私有仓库 + Cloudflare Pages + Cloudflare Access。
- 不要把 token、账号、密码写进项目文件。
- 不要把本地端口暴露到公网。

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
