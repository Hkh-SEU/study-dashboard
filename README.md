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

## 手机端体验

- 首页只作为学习入口：今日复习摘要、三个复习入口。
- 手机端主要使用底部导航切换：`首页`、`计划`、`数学`、`专业课`。
- 桌面端文档页顶部保留快捷导航；手机端隐藏顶部快捷导航，减少重复。
- 左侧 sidebar 会显示数学和专业课错题目录，可以按日期和错题编号跳转。
- 文档顶部默认只显示更新时间，来源路径等信息收进“发布详情”。
- 错题截图可以点击打开原图，方便在手机上双指缩放查看。

## 为什么本地预览不能跨网络访问

- `127.0.0.1` 只代表当前电脑，手机访问自己的 `127.0.0.1` 不会访问到电脑。
- 局域网 IP 只适合同一个 Wi-Fi。
- 不建议把本地电脑端口直接暴露到公网。

如果手机和平板要在不同网络下访问，需要把 `cloud_site` 部署到公网静态托管平台，例如 Cloudflare Pages、GitHub Pages 或 Vercel。

## 多入口访问

建议把访问方式设计成“主站 + 备用站”：

- Cloudflare Pages：主站，当前用于日常访问。
- GitHub Pages：备用站，适合内容可以公开的情况。
- Vercel：备用站，和 Cloudflare 是不同访问链路。

为什么需要多入口：

- `pages.dev` 在某些网络环境下可能不稳定。
- 项目文件没坏时，打不开网址也可能是网络、DNS 或 CDN 链路问题。
- 准备 GitHub Pages 或 Vercel 备用入口，可以在主站打不开时继续复习。

部署成功后，把备用网址填到 `config.json` 的 `deploy.backup_urls` 中。不要把 token、账号或密码写进配置文件。

## 每天怎么用

1. 修改桌面 Markdown 文件：

```text
C:/Desktop/错题本—数学.md
C:/Desktop/错题本—专业课.md
C:/Desktop/今日复习计划.md
```

2. 运行 `一键准备云端发布.py`。

它会自动检查源文件、生成 `cloud_site`、执行部署检查，并告诉你下一步怎么提交。

3. 打开 GitHub Desktop。

4. 左下角 `Summary` 填脚本给出的建议提交信息，例如：

```text
Update study notes 2026-06-13 14:20
```

5. 点击 `Commit to main`。

6. 点击 `Push origin`。

7. 等云平台自动部署，通常 1-2 分钟。

8. 手机优先刷新主站：

```text
https://study-dashboard-pages.pages.dev
```

如果主站打不开，再打开你配置好的 GitHub Pages 或 Vercel 备用站。

如果手机看到旧内容，先强制刷新或等一分钟。  
如果卡片打开后是 Markdown 原文，通常说明 GitHub 或 Cloudflare 还没有部署最新版本。  
如果 `pages.dev` 打不开，可能是当前网络环境问题，不一定是项目失败。

## 本地预览

如果你想先在电脑上看效果：

```text
打开 一键运行学习看板.py，然后点击 VS Code 右上角运行按钮
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

生成并检查云端发布文件：

```powershell
D:\Python3_13\python.exe publish.py --cloud-ready
```

打开公网网址：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

打开第一个已启用的备用网址：

```powershell
D:\Python3_13\python.exe publish.py --open-backup
```

打开所有已配置的网址：

```powershell
D:\Python3_13\python.exe publish.py --open-all
```

当前 `deploy.primary_url` 已填写为 Cloudflare Pages 地址；如果以后换平台或绑定域名，再改成新的网址。

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
    "primary_url": "https://study-dashboard-pages.pages.dev",
    "public_url": "https://study-dashboard-pages.pages.dev",
    "backup_urls": [
      {
        "name": "GitHub Pages",
        "url": "",
        "enabled": false
      },
      {
        "name": "Vercel",
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

- `primary_url`：主站网址，例如 `https://study-dashboard-pages.pages.dev`
- `public_url`：旧字段，保留兼容；如果 `primary_url` 为空，脚本会 fallback 到它
- `backup_urls`：备用站列表。部署 GitHub Pages 或 Vercel 后，把网址填入 `url`，再把 `enabled` 改成 `true`
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
"primary_url": "https://你的项目名.pages.dev"
```

之后可以运行：

```powershell
D:\Python3_13\python.exe publish.py --open-public
```

## GitHub Pages

GitHub Pages 适合公开内容。它可以托管 `cloud_site`，但如果错题本、计划书或截图包含隐私信息，不建议用公开 GitHub Pages。

如果你把 GitHub Pages 作为备用站，部署成功后把网址填到：

```json
{
  "name": "GitHub Pages",
  "url": "https://你的用户名.github.io/study-dashboard/",
  "enabled": true
}
```

## Vercel

Vercel 也可以托管静态站点。连接 GitHub 仓库后，将输出目录设置为：

```text
cloud_site
```

如果你把 Vercel 作为备用站，部署成功后把网址填到：

```json
{
  "name": "Vercel",
  "url": "https://你的项目名.vercel.app",
  "enabled": true
}
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
