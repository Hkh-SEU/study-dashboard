from __future__ import annotations

import argparse
import fnmatch
import html
import http.server
import json
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from setup_vendor import ensure_vendor_assets


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"
DEFAULT_OUTPUT_DIR = "cloud_site"
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((<[^>]+>|[^)]+)\)")
HTML_IMG_PATTERN = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)


@dataclass(frozen=True)
class SiteConfig:
    title: str
    description: str
    output_dir: Path


@dataclass(frozen=True)
class BackupUrl:
    name: str
    url: str
    enabled: bool


@dataclass(frozen=True)
class DeployConfig:
    provider: str
    primary_url: str
    public_url: str
    backup_urls: list[BackupUrl]
    root_directory: str
    output_directory: str
    git_enabled: bool
    default_branch: str


@dataclass(frozen=True)
class DocumentConfig:
    doc_id: str
    title: str
    source: Path
    target: str


@dataclass(frozen=True)
class PublishedDocument:
    title: str
    source: Path
    target: str
    content: str
    modified: str
    size: int


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def is_external_link(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("data:")
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
    )


def is_http_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def primary_public_url(deploy: DeployConfig) -> str:
    return deploy.primary_url or deploy.public_url


def enabled_backup_urls(deploy: DeployConfig) -> list[BackupUrl]:
    return [item for item in deploy.backup_urls if item.enabled and item.url]


def all_access_urls(deploy: DeployConfig) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    primary = primary_public_url(deploy)
    if primary:
        urls.append(("主站", primary))
    urls.extend((item.name, item.url) for item in enabled_backup_urls(deploy))
    return urls


def print_access_entries(deploy: DeployConfig) -> None:
    primary = primary_public_url(deploy)
    print("")
    print("Access entries:")
    if primary:
        print(f"  Primary: {primary}")
    else:
        print("  Primary: not configured")

    backups = enabled_backup_urls(deploy)
    if backups:
        print("  Backups:")
        for item in backups:
            print(f"    - {item.name}: {item.url}")
    else:
        print("  Backups: not configured")


def markdown_url(path: str) -> str:
    return quote(path.replace("\\", "/"), safe="/._-()")


def docsify_route(target: str) -> str:
    route = Path(target).with_suffix("").as_posix().strip("/")
    return f"#/{route}" if route else "#/"


def document_priority(document: PublishedDocument) -> tuple[int, str]:
    stem = Path(document.target).stem.lower()
    priority = {"plan": 0, "math": 1, "major": 2}
    return priority.get(stem, 10), document.title


def document_nav(active_target: str | None = None) -> str:
    items = [
        ("首页", "#/", ""),
        ("今日计划", "#/plan", "plan.md"),
        ("数学", "#/math", "math.md"),
        ("专业课", "#/major", "major.md"),
    ]
    links = []
    active = (active_target or "").lower()
    for label, href, target in items:
        classes = "doc-nav-link"
        if target and active == target:
            classes += " active"
        links.append(f'<a class="{classes}" href="{href}">{label}</a>')
    return '<nav class="doc-nav" aria-label="文档切换">' + "".join(links) + "</nav>"


def mobile_bottom_nav() -> str:
    items = [
        ("首页", "#/", "home"),
        ("计划", "#/plan", "plan"),
        ("数学", "#/math", "math"),
        ("专业课", "#/major", "major"),
    ]
    links = [
        f'<a class="mobile-bottom-nav-link" href="{href}" data-route="{route}">{label}</a>'
        for label, href, route in items
    ]
    return '<nav class="mobile-bottom-nav" aria-label="手机底部导航">' + "".join(links) + "</nav>"


def docsify_anchor_id(title: str) -> str:
    anchor = re.sub(r"\s+", "-", title.strip().lower())
    anchor = re.sub(r"[^\w\-\u4e00-\u9fff]", "", anchor)
    return anchor.strip("-")


def document_route_label(document: PublishedDocument) -> str:
    stem = Path(document.target).stem.lower()
    labels = {
        "plan": "今日计划",
        "math": "数学",
        "major": "专业课",
    }
    return labels.get(stem, document.title)


def strip_markdown_marks(text: str) -> str:
    text = re.sub(r"[*_`#>\[\]]+", "", text)
    text = text.replace("==", "")
    return re.sub(r"\s+", " ", text).strip()


def sanitize_asset_name(value: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .")
    return stem or "asset"


def slugify(value: str, used: set[str]) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value).strip("-_")
    if not stem:
        stem = "document"

    candidate = f"{stem}.md"
    counter = 2
    while candidate.lower() in used:
        candidate = f"{stem}-{counter}.md"
        counter += 1

    used.add(candidate.lower())
    return candidate


def load_raw_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_backup_urls(raw_value: Any) -> list[BackupUrl]:
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError("deploy.backup_urls must be a list")

    backup_urls: list[BackupUrl] = []
    for index, item in enumerate(raw_value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"deploy.backup_urls #{index} must be an object")
        name = str(item.get("name", f"Backup {index}")).strip() or f"Backup {index}"
        url = str(item.get("url", "")).strip()
        enabled = bool(item.get("enabled", False))
        backup_urls.append(BackupUrl(name=name, url=url, enabled=enabled))
    return backup_urls


def load_config() -> tuple[SiteConfig, list[DocumentConfig], DeployConfig]:
    raw = load_raw_config()
    site_raw = raw.get("site", {})
    output_dir_name = str(site_raw.get("output_dir", DEFAULT_OUTPUT_DIR)).strip() or DEFAULT_OUTPUT_DIR
    site = SiteConfig(
        title=str(site_raw.get("title", "学习文件看板")).strip() or "学习文件看板",
        description=str(site_raw.get("description", "")).strip(),
        output_dir=PROJECT_DIR / output_dir_name,
    )

    deploy_raw = raw.get("deploy", {})
    public_url = str(deploy_raw.get("public_url", "")).strip()
    primary_url = str(deploy_raw.get("primary_url", "")).strip() or public_url
    deploy = DeployConfig(
        provider=str(deploy_raw.get("provider", "cloudflare_pages")).strip() or "cloudflare_pages",
        primary_url=primary_url,
        public_url=public_url,
        backup_urls=load_backup_urls(deploy_raw.get("backup_urls", [])),
        root_directory=str(deploy_raw.get("root_directory", "study_tools/study-dashboard")).strip(),
        output_directory=str(deploy_raw.get("output_directory", output_dir_name)).strip() or output_dir_name,
        git_enabled=bool(deploy_raw.get("git_enabled", False)),
        default_branch=str(deploy_raw.get("default_branch", "main")).strip() or "main",
    )

    scan_raw = raw.get("scan", {})
    if isinstance(scan_raw, dict) and scan_raw.get("enabled"):
        documents = scan_documents(scan_raw)
    else:
        documents = configured_documents(raw.get("documents", []))

    if not documents:
        raise ValueError("No Markdown documents configured or scanned.")

    return site, documents, deploy


def configured_documents(raw_documents: Any) -> list[DocumentConfig]:
    if not isinstance(raw_documents, list):
        raise ValueError("config.documents must be a list")

    documents: list[DocumentConfig] = []
    used_targets: set[str] = set()

    for index, item in enumerate(raw_documents, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"document #{index} must be an object")

        doc_id = str(item.get("id", "")).strip() or f"doc-{index}"
        title = str(item.get("title", doc_id)).strip() or doc_id
        source = Path(str(item.get("source", "")).strip()).expanduser()
        target = str(item.get("target", "")).strip()

        if not str(source):
            raise ValueError(f"document {doc_id} has no source")
        if not target:
            target = slugify(doc_id, used_targets)
        elif not target.lower().endswith(".md"):
            target = f"{target}.md"

        lower_target = target.lower()
        if lower_target in used_targets:
            raise ValueError(f"duplicate target file: {target}")
        used_targets.add(lower_target)

        documents.append(DocumentConfig(doc_id=doc_id, title=title, source=source, target=target))

    return documents


def scan_documents(scan_raw: dict[str, Any]) -> list[DocumentConfig]:
    directory = Path(str(scan_raw.get("directory", "")).strip()).expanduser()
    if not directory.exists():
        raise FileNotFoundError(f"scan.directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"scan.directory is not a directory: {directory}")

    patterns = scan_raw.get("patterns", ["*.md"])
    excludes = scan_raw.get("exclude", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ValueError("scan.patterns must be a list of strings")
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise ValueError("scan.exclude must be a list of strings")

    matched: list[Path] = []
    for pattern in patterns:
        matched.extend(path for path in directory.glob(pattern) if path.is_file())

    filtered = []
    for path in sorted(set(matched), key=lambda item: item.name.lower()):
        rel = path.relative_to(directory).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in excludes):
            continue
        if path.suffix.lower() not in {".md", ".markdown"}:
            continue
        filtered.append(path)

    used_targets: set[str] = set()
    return [
        DocumentConfig(
            doc_id=path.stem,
            title=path.stem,
            source=path,
            target=slugify(path.stem, used_targets),
        )
        for path in filtered
    ]


def validate_source(document: DocumentConfig) -> PublishedDocument:
    source = document.source
    if not source.exists():
        raise FileNotFoundError(f"{document.title}: source file does not exist: {source}")
    if source.is_dir():
        raise IsADirectoryError(f"{document.title}: source path is a directory: {source}")

    content = read_text(source)
    if not content.strip():
        raise ValueError(f"{document.title}: source file is empty: {source}")

    stat = source.stat()
    return PublishedDocument(
        title=document.title,
        source=source,
        target=document.target,
        content=content.strip() + "\n",
        modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        size=stat.st_size,
    )


def collect_documents() -> tuple[SiteConfig, list[PublishedDocument], DeployConfig]:
    site, documents, deploy = load_config()
    return site, [validate_source(document) for document in documents], deploy


def clean_generated(output_dir: Path) -> None:
    if not output_dir.exists():
        return

    protected = {"README.md", "_sidebar.md"}
    for path in output_dir.glob("*.md"):
        if path.name not in protected:
            path.unlink()

    media_dir = output_dir / "assets" / "media"
    if media_dir.exists():
        shutil.rmtree(media_dir)


def ensure_output(output_dir: Path, clean: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assets").mkdir(parents=True, exist_ok=True)
    if clean:
        clean_generated(output_dir)
    ensure_vendor_assets(output_dir)


def strip_duplicate_title(content: str, title: str) -> str:
    lines = content.lstrip().splitlines()
    if lines and lines[0].strip() == f"# {title}":
        return "\n".join(lines[1:]).lstrip() + "\n"
    return content


def build_document_markdown(document: PublishedDocument, published_at: str) -> str:
    content = strip_duplicate_title(document.content, document.title)
    return f"""# {document.title}

{document_nav(document.target)}

<div class="publish-meta">
  <span>更新：{published_at}</span>
</div>

<details class="publish-details">
  <summary>发布详情</summary>
  <div>来源：{html.escape(document.source.as_posix())}</div>
  <div>源文件最后修改：{document.modified}</div>
  <div>发布时间：{published_at}</div>
</details>

---

{content}"""


def extract_problem_sections(document: PublishedDocument) -> list[tuple[str, list[str]]]:
    content = strip_duplicate_title(document.content, document.title)
    if Path(document.target).stem.lower() not in {"math", "major"}:
        return []

    sections: list[tuple[str, list[str]]] = []
    for line in content.splitlines():
        date_match = re.match(r"^##\s+(.+?)\s*$", line)
        if date_match:
            title = strip_markdown_marks(date_match.group(1))
            if re.search(r"\d{1,2}[-/.]\d{1,2}", title):
                sections.append((title, []))
            continue

        problem_match = re.match(r"^###\s+(.+?)\s*$", line)
        if problem_match and "错题" in problem_match.group(1):
            title = strip_markdown_marks(problem_match.group(1))
            if not sections:
                sections.append(("本页", []))
            sections[-1][1].append(title)

    return [(date, items) for date, items in sections if items]


def resolve_asset_path(raw_ref: str, source: Path) -> Path | None:
    ref = raw_ref.strip()
    if ref.startswith("<") and ref.endswith(">"):
        ref = ref[1:-1].strip()
    if is_external_link(ref):
        return None

    ref_path = Path(ref)
    if ref_path.is_absolute():
        return ref_path
    return (source.parent / ref_path).resolve()


def copy_and_rewrite_assets(content: str, source: Path, output_dir: Path, target_name: str) -> str:
    media_dir = output_dir / "assets" / "media" / Path(target_name).stem
    used_names: set[str] = set()

    def copy_asset(raw_ref: str) -> str:
        resolved = resolve_asset_path(raw_ref, source)
        if resolved is None or not resolved.exists() or resolved.is_dir():
            return raw_ref

        media_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_asset_name(resolved.name)
        candidate = safe_name
        counter = 2
        while candidate.lower() in used_names:
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        used_names.add(candidate.lower())

        target = media_dir / candidate
        shutil.copy2(resolved, target)
        return markdown_url(target.relative_to(output_dir).as_posix())

    def replace_markdown(match: re.Match[str]) -> str:
        alt = match.group(1)
        rewritten = copy_asset(match.group(2))
        if rewritten == match.group(2) or is_external_link(rewritten):
            return f"![{alt}]({rewritten})"
        escaped_alt = html.escape(alt or "题目截图", quote=True)
        escaped_ref = html.escape(rewritten, quote=True)
        return f'<a class="image-link" href="{escaped_ref}" target="_blank" rel="noopener"><img src="{escaped_ref}" alt="{escaped_alt}"></a>'

    def replace_html(match: re.Match[str]) -> str:
        rewritten = copy_asset(match.group(2))
        return f"{match.group(1)}{rewritten}{match.group(3)}"

    content = IMAGE_PATTERN.sub(replace_markdown, content)
    return HTML_IMG_PATTERN.sub(replace_html, content)


def extract_plan_summary(documents: list[PublishedDocument]) -> dict[str, str]:
    plan = next((document for document in documents if Path(document.target).stem.lower() == "plan"), None)
    if plan is None:
        return {"提示": "打开今日复习计划查看任务"}

    text = strip_markdown_marks(plan.content)
    summary: dict[str, str] = {}

    total_match = re.search(r"今日[：:]\s*(\d+)\s*道", text)
    if total_match:
        summary["今日任务"] = f"{total_match.group(1)} 道"

    done_match = re.search(r"(\d+\s*/\s*\d+)\s*已完成", text)
    if done_match:
        summary["已完成"] = done_match.group(1).replace(" ", "")

    math_match = re.search(r"数学\s*(\d+\s*/\s*\d+)", text)
    if math_match:
        summary["数学"] = math_match.group(1).replace(" ", "")

    major_match = re.search(r"专业课\s*(\d+\s*/\s*\d+)", text)
    if major_match:
        summary["专业课"] = major_match.group(1).replace(" ", "")

    return summary or {"提示": "打开今日复习计划查看任务"}


def build_plan_summary(documents: list[PublishedDocument]) -> str:
    summary = extract_plan_summary(documents)
    items = "\n".join(
        f'<div class="summary-chip"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in summary.items()
    )
    return f'<div class="today-summary">{items}</div>'


def build_home(site: SiteConfig, documents: list[PublishedDocument], published_at: str) -> str:
    ordered_documents = sorted(documents, key=document_priority)
    cards = "\n".join(
        f'<a class="study-card" href="{html.escape(docsify_route(document.target))}">'
        f'<strong>{html.escape(document.title)}</strong>'
        "</a>"
        for document in ordered_documents
    )

    return f"""# {site.title}

{build_plan_summary(documents)}

<div class="study-card-grid">
{cards}
</div>

<p class="home-updated">更新：{published_at}</p>
"""


def build_sidebar(documents: list[PublishedDocument]) -> str:
    ordered_documents = sorted(documents, key=document_priority)
    lines = ["- [首页](#/)"]
    for document in ordered_documents:
        route = docsify_route(document.target)
        lines.append(f"- [{document_route_label(document)}]({route})")
        for date, problems in extract_problem_sections(document):
            lines.append(f"  - {date}")
            for problem in problems:
                anchor = docsify_anchor_id(problem)
                lines.append(f"    - [{problem}]({route}?id={anchor})")
    return "\n".join(lines) + "\n"


def build_index(site: SiteConfig) -> str:
    title = html.escape(site.title)
    description = html.escape(site.description)
    js_title = json.dumps(site.title, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="{description}" />
    <title>{title}</title>
    <link rel="stylesheet" href="assets/vendor/docsify/vue.css" />
    <link rel="stylesheet" href="assets/cloud.css" />
  </head>
  <body>
    <div id="app">加载中...</div>
    {mobile_bottom_nav()}
    <script>
      window.$docsify = {{
        name: {js_title},
        loadSidebar: true,
        subMaxLevel: 0,
        auto2top: true,
        search: {{
          maxAge: 86400000,
          paths: "auto",
          placeholder: "搜索错题、知识点、计划...",
          noData: "没有找到相关内容",
          depth: 4
        }}
      }};
      function updateBottomNav() {{
        var hash = window.location.hash || "#/";
        var route = hash.indexOf("#/plan") === 0 ? "plan" :
          hash.indexOf("#/math") === 0 ? "math" :
          hash.indexOf("#/major") === 0 ? "major" : "home";
        document.querySelectorAll(".mobile-bottom-nav-link").forEach(function (item) {{
          item.classList.toggle("active", item.dataset.route === route);
        }});
      }}
      window.addEventListener("hashchange", updateBottomNav);
      window.addEventListener("DOMContentLoaded", updateBottomNav);
    </script>
    <script src="assets/vendor/docsify/docsify.min.js"></script>
    <script src="assets/vendor/docsify/search.min.js"></script>
  </body>
</html>
"""


def build_css() -> str:
    return """:root {
  --theme-color: #1d7a68;
  --content-max-width: 920px;
  --line-soft: #dfe4da;
  --surface: #ffffff;
  --surface-soft: #eef6f3;
  --ink: #20241f;
  --muted: #6b7268;
}

body {
  color: var(--ink);
  background: #f7f8f5;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}

.app-name-link {
  color: #1d7a68;
  font-weight: 800;
}

.sidebar {
  border-right: 1px solid var(--line-soft);
  background: #fff;
}

.sidebar ul li a {
  color: #39413b;
  line-height: 1.65;
}

.sidebar ul li.active > a {
  color: #1d7a68;
  border-right-color: #1d7a68;
  font-weight: 700;
}

.content {
  padding-top: 12px;
}

.mobile-bottom-nav {
  display: none;
}

.markdown-section {
  max-width: var(--content-max-width);
  padding: 28px 28px 56px;
  line-height: 1.72;
  font-size: 16px;
}

.markdown-section h1,
.markdown-section h2,
.markdown-section h3,
.markdown-section h4 {
  color: #17211d;
  letter-spacing: 0;
}

.markdown-section h1 {
  font-size: 1.86rem;
  margin-bottom: 1.1rem;
}

.markdown-section h2 {
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: 0.36rem;
  font-size: 1.45rem;
  margin-top: 2.1rem;
}

.markdown-section h3 {
  margin-top: 1.55rem;
  font-size: 1.18rem;
}

.markdown-section h2[id^="-"],
.markdown-section h2[id^="_"] {
  color: #1d564c;
}

.markdown-section h2 {
  scroll-margin-top: 18px;
}

.markdown-section h3 {
  scroll-margin-top: 18px;
}

.markdown-section h3[id*="错题"],
.markdown-section h3:has(a[href*="错题"]) {
  border-left: 4px solid #1d7a68;
  padding-left: 10px;
  color: #1d342f;
}

.markdown-section a {
  color: #1d7a68;
}

.markdown-section p a:has(img),
.markdown-section a:has(img),
.image-link {
  display: block;
  border-bottom: 0;
}

.markdown-section blockquote {
  border-left: 4px solid #1d7a68;
  color: #39413b;
  background: #e8f4f1;
}

.markdown-section code {
  border-radius: 4px;
  color: #20362f;
  background: #eef2ec;
  overflow-wrap: anywhere;
}

.markdown-section pre {
  border-radius: 8px;
  background: #eef2ec;
  overflow-x: auto;
  white-space: pre;
  -webkit-overflow-scrolling: touch;
}

.markdown-section table {
  display: block;
  width: 100%;
  overflow-x: auto;
  white-space: nowrap;
  -webkit-overflow-scrolling: touch;
}

.markdown-section img,
.image-link img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 12px auto 18px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fff;
}

.markdown-section a img,
.image-link img {
  cursor: zoom-in;
}

.markdown-section ul,
.markdown-section ol {
  padding-left: 1.35rem;
}

.markdown-section li {
  margin: 0.28rem 0;
}

.markdown-section li input[type="checkbox"] {
  width: 1.05em;
  height: 1.05em;
  margin: 0 0.38em 0.18em -1.15em;
  vertical-align: middle;
  accent-color: #1d7a68;
}

.markdown-section li:has(input[type="checkbox"]) {
  list-style: none;
  margin: 0.14rem 0 0.14rem 0.15rem;
  padding: 0.08rem 0.24rem;
  border-radius: 6px;
}

.markdown-section li:has(input[type="checkbox"]:checked) {
  color: #5f6963;
  background: #f1f5ef;
}

.publish-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0 16px;
  color: #4e5b55;
  font-size: 0.82rem;
}

.publish-meta span {
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  padding: 3px 8px;
  background: #f2f6f3;
  line-height: 1.45;
}

.publish-details {
  margin: -8px 0 18px;
  color: var(--muted);
  font-size: 0.78rem;
}

.publish-details summary {
  cursor: pointer;
  width: fit-content;
  color: #5e6a63;
}

.publish-details div {
  margin-top: 4px;
  overflow-wrap: anywhere;
}

.doc-nav {
  display: flex;
  gap: 8px;
  margin: -4px 0 10px;
  padding-bottom: 4px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.doc-nav-link {
  flex: 0 0 auto;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  padding: 5px 11px;
  color: #1d564c;
  background: #fff;
  font-size: 0.88rem;
  font-weight: 700;
  text-decoration: none;
}

.doc-nav-link.active {
  border-color: #1d7a68;
  color: #fff;
  background: #1d7a68;
}

.markdown-section th {
  background: #f2f5ef;
}

.markdown-section tr {
  border-top: 1px solid var(--line-soft);
}

.markdown-section td,
.markdown-section th {
  border: 1px solid var(--line-soft);
  padding: 8px 10px;
}

.search {
  border-bottom: 1px solid var(--line-soft);
}

.search input {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 8px 10px;
}

.search .matching-post {
  padding: 8px 2px;
}

.search .matching-post h2 {
  line-height: 1.35;
}

.search .matching-post p {
  line-height: 1.5;
}

.study-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0 24px;
}

.study-card {
  display: block;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 10px 14px;
  color: var(--ink);
  background: var(--surface);
  text-decoration: none;
}

.study-card:hover {
  border-color: #1d7a68;
}

.study-card strong {
  display: block;
  margin-bottom: 0;
  color: #1d7a68;
  font-size: 1rem;
}

.home-updated {
  margin-top: -8px;
  color: var(--muted);
  font-size: 0.78rem;
  text-align: right;
}

.today-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 18px;
}

.summary-chip {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
}

.summary-chip span {
  display: block;
  margin-bottom: 3px;
  color: var(--muted);
  font-size: 0.78rem;
}

.summary-chip strong {
  display: block;
  color: #20362f;
  font-size: 1rem;
}

@media (max-width: 768px) {
  body {
    background: #fbfcf8;
  }

  .content {
    padding-top: 8px;
  }

  .markdown-section {
    padding: 16px 14px 96px;
    font-size: 16px;
    line-height: 1.76;
  }

  .markdown-section h1 {
    font-size: 1.48rem;
    line-height: 1.25;
  }

  .markdown-section h2 {
    font-size: 1.22rem;
    margin-top: 1.9rem;
  }

  .markdown-section h3 {
    font-size: 1.06rem;
    margin-top: 1.25rem;
  }

  .markdown-section img,
  .image-link img {
    width: 100%;
    border-radius: 6px;
    margin: 10px auto 16px;
  }

  .markdown-section table {
    font-size: 0.92rem;
  }

  .markdown-section pre {
    font-size: 0.88rem;
  }

  .markdown-section ul,
  .markdown-section ol {
    padding-left: 1.18rem;
  }

  .sidebar {
    padding-top: 18px;
  }

  .sidebar-toggle {
    padding: 18px 22px 10px 12px;
  }

  .study-card-grid {
    grid-template-columns: 1fr;
    gap: 7px;
    margin: 12px 0 20px;
  }

  .today-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px;
    margin: 10px 0 14px;
  }

  .summary-chip {
    padding: 8px 10px;
  }

  .study-card {
    padding: 9px 11px;
  }

  .study-card strong {
    margin-bottom: 2px;
  }

  .doc-nav {
    display: none;
  }

  .publish-meta {
    gap: 4px;
    margin: 4px 0 12px;
    font-size: 0.78rem;
  }

  .publish-meta span {
    display: inline-block;
    max-width: 100%;
    margin-bottom: 4px;
    border-radius: 6px;
    padding: 3px 6px;
    overflow-wrap: anywhere;
  }

  .publish-details {
    margin: -8px 0 14px;
    font-size: 0.74rem;
  }

  .mobile-bottom-nav {
    position: fixed;
    right: 12px;
    bottom: max(12px, env(safe-area-inset-bottom));
    left: 12px;
    z-index: 40;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 2px;
    border: 1px solid rgba(29, 122, 104, 0.16);
    border-radius: 14px;
    padding: 5px;
    background: rgba(255, 255, 255, 0.94);
    box-shadow: 0 8px 24px rgba(24, 47, 40, 0.12);
    backdrop-filter: blur(8px);
  }

  .mobile-bottom-nav-link {
    position: relative;
    border-radius: 10px;
    padding: 7px 4px 8px;
    color: #1d564c;
    font-size: 0.78rem;
    font-weight: 800;
    text-align: center;
    text-decoration: none;
  }

  .mobile-bottom-nav-link.active {
    color: #1d7a68;
    background: #edf7f4;
  }

  .mobile-bottom-nav-link.active::after {
    position: absolute;
    right: 28%;
    bottom: 3px;
    left: 28%;
    height: 2px;
    border-radius: 999px;
    background: #1d7a68;
    content: "";
  }
}
"""


def publish(clean: bool) -> tuple[SiteConfig, list[PublishedDocument], DeployConfig]:
    site, documents, deploy = collect_documents()
    ensure_output(site.output_dir, clean=clean)
    published_at = now_text()

    for document in documents:
        rewritten_content = copy_and_rewrite_assets(
            document.content,
            source=document.source,
            output_dir=site.output_dir,
            target_name=document.target,
        )
        output_document = PublishedDocument(
            title=document.title,
            source=document.source,
            target=document.target,
            content=rewritten_content,
            modified=document.modified,
            size=document.size,
        )
        (site.output_dir / document.target).write_text(build_document_markdown(output_document, published_at), encoding="utf-8")

    (site.output_dir / "README.md").write_text(build_home(site, documents, published_at), encoding="utf-8")
    (site.output_dir / "_sidebar.md").write_text(build_sidebar(documents), encoding="utf-8")
    (site.output_dir / "index.html").write_text(build_index(site), encoding="utf-8")
    (site.output_dir / ".nojekyll").write_text("", encoding="utf-8")
    (site.output_dir / "assets" / "cloud.css").write_text(build_css(), encoding="utf-8")

    print_report(site, documents, generated=True, published_at=published_at)
    print_next_steps(site, deploy)
    return site, documents, deploy


def check_only() -> tuple[SiteConfig, list[PublishedDocument], DeployConfig]:
    site, documents, deploy = collect_documents()
    print_report(site, documents, generated=False, published_at=now_text())
    print("Check passed. No files were generated.")
    return site, documents, deploy


def print_report(site: SiteConfig, documents: list[PublishedDocument], generated: bool, published_at: str) -> None:
    print("")
    print("Study Dashboard Publisher")
    print(f"Site: {site.title}")
    print(f"Output: {site.output_dir.relative_to(PROJECT_DIR).as_posix()}")
    print(f"Published at: {published_at}")
    print(f"Mode: {'generated static site' if generated else 'check only'}")
    print("")

    for document in documents:
        print(f"- {document.title}")
        print(f"  Source: {document.source.as_posix()}")
        print(f"  Target: {(site.output_dir / document.target).relative_to(PROJECT_DIR).as_posix()}")
        print(f"  Size: {document.size} bytes")
        print(f"  Last modified: {document.modified}")


def required_deploy_files(site: SiteConfig, documents: list[PublishedDocument]) -> list[Path]:
    output = site.output_dir
    required = [
        output / "index.html",
        output / "README.md",
        output / "_sidebar.md",
        output / "assets" / "cloud.css",
        output / "assets" / "vendor" / "docsify" / "vue.css",
        output / "assets" / "vendor" / "docsify" / "docsify.min.js",
        output / "assets" / "vendor" / "docsify" / "search.min.js",
    ]
    required.extend(output / document.target for document in documents)
    return required


def markdown_image_refs(text: str) -> list[str]:
    refs = []
    for match in IMAGE_PATTERN.finditer(text):
        ref = match.group(2).strip()
        if ref.startswith("<") and ref.endswith(">"):
            ref = ref[1:-1].strip()
        refs.append(ref)
    for match in HTML_IMG_PATTERN.finditer(text):
        refs.append(match.group(2).strip())
    return refs


def direct_markdown_link_errors(output: Path) -> list[str]:
    errors: list[str] = []
    checked_files = [output / "README.md", output / "_sidebar.md"]
    direct_patterns = [
        "(math.md)",
        "(major.md)",
        "(plan.md)",
        'href="math.md"',
        'href="major.md"',
        'href="plan.md"',
        "href='math.md'",
        "href='major.md'",
        "href='plan.md'",
    ]
    for path in checked_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in direct_patterns:
            if pattern in text:
                errors.append(f"{path.relative_to(PROJECT_DIR).as_posix()} contains direct Markdown link: {pattern}")
    return errors


def check_deploy_files(site: SiteConfig, documents: list[PublishedDocument], deploy: DeployConfig) -> bool:
    errors: list[str] = []
    warnings: list[str] = []
    output = site.output_dir

    for path in required_deploy_files(site, documents):
        if not path.exists():
            errors.append(f"Missing: {path.relative_to(PROJECT_DIR).as_posix()}")
        elif path.is_file() and path.stat().st_size == 0:
            errors.append(f"Empty file: {path.relative_to(PROJECT_DIR).as_posix()}")

    for document in documents:
        target = output / document.target
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        for ref in markdown_image_refs(text):
            if is_external_link(ref):
                continue
            asset_path = output / unquote(ref)
            if not asset_path.exists():
                errors.append(f"Missing image asset referenced by {document.target}: {ref}")

    errors.extend(direct_markdown_link_errors(output))

    primary = primary_public_url(deploy)
    if primary and not is_http_url(primary):
        errors.append(f"Primary URL should start with http:// or https://: {primary}")

    for backup in deploy.backup_urls:
        if backup.url and not is_http_url(backup.url):
            errors.append(f"Backup URL should start with http:// or https://: {backup.name}: {backup.url}")
        if backup.enabled and not backup.url:
            warnings.append(f"Backup entry is enabled but has no URL: {backup.name}")

    files = [path for path in output.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)

    print("")
    print("Deploy check")
    print(f"Provider: {deploy.provider}")
    print(f"Output directory: {deploy.output_directory}")
    print(f"Root directory: {deploy.root_directory or '(repository root)'}")
    print(f"Files: {len(files)}")
    print(f"Total size: {format_size(total_size)}")
    print_access_entries(deploy)
    print("")
    print("Privacy reminder: cloud_site contains your study notes, plan, screenshots, and copied media.")
    print("If the repository or hosted site is public, these materials may become public.")

    if warnings:
        print("")
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if errors:
        print("")
        print("Deploy check failed:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("")
    print("Deploy check passed. cloud_site is ready for static hosting.")
    return True


def doctor() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    print("")
    print("Study Dashboard Doctor")
    print("")

    print(f"[1/6] Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        errors.append("Python 3.10 or newer is recommended.")

    print(f"[2/6] Config: {CONFIG_PATH.relative_to(PROJECT_DIR).as_posix()}")
    try:
        raw = load_raw_config()
        site, configured, deploy = load_config()
    except Exception as exc:  # noqa: BLE001
        print(f"      FAILED: {exc}")
        errors.append(f"config.json error: {exc}")
        raw = {}
        site = None
        configured = []
        deploy = None
    else:
        print(f"      Site: {site.title}")
        if not isinstance(raw.get("site"), dict):
            warnings.append("config.site is missing or not an object.")
        if not isinstance(raw.get("documents"), list):
            errors.append("config.documents must be a list.")
        if not isinstance(raw.get("deploy"), dict):
            warnings.append("config.deploy is missing or not an object.")

    print("[3/6] Source Markdown files")
    documents: list[PublishedDocument] = []
    for document in configured:
        try:
            published = validate_source(document)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{document.title}: {exc}")
            print(f"      FAILED {document.title}: {exc}")
            continue
        documents.append(published)
        print(f"      OK {document.title}: {document.source.as_posix()}")

    print("[4/6] cloud_site files")
    if site is None:
        errors.append("Cannot check cloud_site because config failed.")
    else:
        missing = []
        for path in required_deploy_files(site, documents):
            if not path.exists():
                missing.append(path.relative_to(PROJECT_DIR).as_posix())
            elif path.is_file() and path.stat().st_size == 0:
                errors.append(f"Empty generated file: {path.relative_to(PROJECT_DIR).as_posix()}")
        if missing:
            warnings.append("cloud_site is incomplete. Run publish.py --clean to generate it.")
            for item in missing[:8]:
                print(f"      Missing: {item}")
        else:
            print("      OK key files exist.")

    print("[5/6] Docsify local assets")
    if site is not None:
        vendor_files = [
            site.output_dir / "assets" / "vendor" / "docsify" / "vue.css",
            site.output_dir / "assets" / "vendor" / "docsify" / "docsify.min.js",
            site.output_dir / "assets" / "vendor" / "docsify" / "search.min.js",
        ]
        for path in vendor_files:
            if path.exists() and path.stat().st_size > 0:
                print(f"      OK {path.relative_to(PROJECT_DIR).as_posix()}")
            else:
                errors.append(f"Missing docsify asset: {path.relative_to(PROJECT_DIR).as_posix()}")

    print("[6/6] Public URLs and routes")
    if deploy is None:
        errors.append("Cannot check deploy URLs because config failed.")
    else:
        primary = primary_public_url(deploy)
        if primary:
            print(f"      Primary URL: {primary}")
            if not is_http_url(primary):
                errors.append(f"deploy.primary_url should start with http:// or https://: {primary}")
        else:
            warnings.append("deploy.primary_url is empty. Fill it after Cloudflare Pages deployment.")

        if deploy.public_url:
            print("      Legacy public_url: configured")
        else:
            print("      Legacy public_url: empty")

        if deploy.backup_urls:
            enabled_count = 0
            for backup in deploy.backup_urls:
                state = "enabled" if backup.enabled else "disabled"
                value = backup.url or "not configured"
                print(f"      Backup {backup.name}: {state}, {value}")
                if backup.url and not is_http_url(backup.url):
                    errors.append(f"deploy.backup_urls {backup.name} should start with http:// or https://.")
                if backup.enabled and backup.url:
                    enabled_count += 1
            if enabled_count == 0:
                warnings.append("No backup public entry is enabled. Add GitHub Pages or Vercel if pages.dev is unstable.")
        else:
            warnings.append("deploy.backup_urls is empty. Add GitHub Pages or Vercel if pages.dev is unstable.")

        if primary and not enabled_backup_urls(deploy):
            warnings.append("当前只有一个公网入口。如果 pages.dev 在某些网络下不稳定，建议增加 GitHub Pages 或 Vercel 备用入口。")

        if site is not None:
            route_errors = direct_markdown_link_errors(site.output_dir)
            errors.extend(route_errors)
            if route_errors:
                for item in route_errors:
                    print(f"      FAILED {item}")
            else:
                print("      OK docsify routes use #/ links.")

    if warnings:
        print("")
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if errors:
        print("")
        print("Doctor result: needs attention")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("")
    print("Doctor result: OK, 可以发布。")
    return 0


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def print_next_steps(site: SiteConfig, deploy: DeployConfig) -> None:
    output = site.output_dir.relative_to(PROJECT_DIR).as_posix()
    print("")
    print("Next steps:")
    print_access_entries(deploy)
    print("  Local preview:")
    print("    D:\\Python3_13\\python.exe publish.py --preview")
    print("  Cloud-ready check:")
    print("    D:\\Python3_13\\python.exe publish.py --deploy-check")
    print("  Manual Git publish:")
    print(f"    git add {output}")
    print('    git commit -m "Update study dashboard"')
    print("    git push")
    print("  Cloudflare Pages:")
    print(f"    Root directory: {deploy.root_directory or '(repository root)'}")
    print("    Build command: leave empty")
    print(f"    Build output directory: {deploy.output_directory}")
    print("  Privacy:")
    print("    Public repositories or public Pages sites are not suitable for private study notes.")
    if not primary_public_url(deploy):
        print("  Public URL:")
        print("    部署完成后，把主站网址填入 config.json 的 deploy.primary_url，就可以用 --open-public 打开。")
    if not enabled_backup_urls(deploy):
        print("  Backup URLs:")
        print("    如果 pages.dev 不稳定，可以把 GitHub Pages 或 Vercel 网址填入 deploy.backup_urls。")


def print_cloud_instructions(deploy: DeployConfig) -> None:
    print("")
    print("Cloud deployment instructions")
    print("")
    print("Cloudflare Pages (recommended):")
    print("  1. Push this project to GitHub.")
    print("  2. Create a Cloudflare Pages project and connect the GitHub repository.")
    print(f"  3. Root directory: {deploy.root_directory or '(repository root)'}")
    print("  4. Build command: leave empty")
    print(f"  5. Build output directory: {deploy.output_directory}")
    print("  6. After deployment, copy the pages.dev URL into config.json deploy.primary_url.")
    print("")
    print("GitHub Pages:")
    print("  Use only if the content can be public, or if you have a suitable private Pages setup.")
    print("")
    print("Vercel:")
    print(f"  Connect the repository and set output directory to {deploy.output_directory}.")
    print("  After deployment, copy the Vercel URL into config.json deploy.backup_urls.")


def confirm_git_publish(message: str, yes: bool) -> bool:
    print("")
    print("cloud_site contains your study notes, review plan, screenshots, and copied media.")
    print("If your repository is public, these files may become public.")
    print(f'Commit message: "{message}"')
    if yes:
        return True
    return input("Continue with git add/commit/push? Type y to proceed: ").strip().lower() == "y"


def run_git_publish(output_dir: Path, message: str, yes: bool) -> None:
    if not confirm_git_publish(message, yes):
        print("Git publish cancelled.")
        return

    output = output_dir.relative_to(PROJECT_DIR).as_posix()
    commands = [
        ["git", "add", output],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    for command in commands:
        print(f"Running: {' '.join(command)}")
        subprocess.run(command, cwd=PROJECT_DIR, check=True)


def open_public_url() -> int:
    _, _, deploy = load_config()
    url = primary_public_url(deploy)
    if not url:
        print("deploy.primary_url is empty.")
        print("部署完成后，把主站网址填入 config.json 的 deploy.primary_url，就可以用 --open-public 打开。")
        return 1
    print(f"Opening primary URL: {url}")
    webbrowser.open(url)
    return 0


def open_backup_url() -> int:
    _, _, deploy = load_config()
    backups = enabled_backup_urls(deploy)
    if not backups:
        print("No enabled backup URL is configured.")
        print("部署 GitHub Pages 或 Vercel 后，把网址填入 config.json 的 deploy.backup_urls。")
        return 1
    backup = backups[0]
    print(f"Opening backup URL: {backup.name}: {backup.url}")
    webbrowser.open(backup.url)
    return 0


def open_all_urls() -> int:
    _, _, deploy = load_config()
    urls = all_access_urls(deploy)
    if not urls:
        print("No public URL is configured.")
        print("请先填写 deploy.primary_url，或启用 deploy.backup_urls 中的备用网址。")
        return 1
    for name, url in urls:
        print(f"Opening {name}: {url}")
        webbrowser.open(url)
    return 0


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def preview(output_dir: Path, port: int = 8080) -> None:
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(output_dir), **kwargs)
    with socketserver.TCPServer(("127.0.0.1", port), handler) as server:
        url = f"http://127.0.0.1:{port}/#/"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print("")
        print(f"Local preview: {url}")
        print("This is only for this computer. For different networks, deploy cloud_site to a static hosting platform.")
        print("Press Ctrl+C to stop.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("")
            print("Stopping preview...")
            server.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish local Markdown files as a docsify static site.")
    parser.add_argument("--check", action="store_true", help="Check config and source files without generating.")
    parser.add_argument("--preview", action="store_true", help="Generate then start a local static preview server.")
    parser.add_argument("--deploy-check", action="store_true", help="Check whether cloud_site is ready for cloud deployment.")
    parser.add_argument("--doctor", action="store_true", help="Run local diagnostics for daily publishing.")
    parser.add_argument("--cloud-ready", action="store_true", help="Generate cloud_site, run deploy-check, and print cloud deployment steps.")
    parser.add_argument("--open-public", action="store_true", help="Open deploy.primary_url from config.json.")
    parser.add_argument("--open-backup", action="store_true", help="Open the first enabled backup URL from config.json.")
    parser.add_argument("--open-all", action="store_true", help="Open the primary URL and all enabled backup URLs from config.json.")
    parser.add_argument("--git", action="store_true", help="Run git add/commit/push after generation.")
    parser.add_argument("--message", default="Update study dashboard", help="Commit message used with --git.")
    parser.add_argument("--yes", action="store_true", help="Skip --git confirmation.")
    parser.add_argument("--clean", action="store_true", help="Clean old generated Markdown and copied media before publishing.")
    args = parser.parse_args()

    try:
        if args.open_public:
            return open_public_url()

        if args.open_backup:
            return open_backup_url()

        if args.open_all:
            return open_all_urls()

        if args.doctor:
            return doctor()

        if args.deploy_check:
            site, documents, deploy = collect_documents()
            return 0 if check_deploy_files(site, documents, deploy) else 1

        if args.cloud_ready:
            site, documents, deploy = publish(clean=True)
            ok = check_deploy_files(site, documents, deploy)
            print_cloud_instructions(deploy)
            if args.git and ok:
                run_git_publish(site.output_dir, args.message, args.yes)
            return 0 if ok else 1

        if args.check:
            check_only()
            return 0

        site, _, deploy = publish(clean=args.clean)
        if args.git:
            run_git_publish(site.output_dir, args.message, args.yes)
        if args.preview:
            preview(site.output_dir)
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"Publish failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
