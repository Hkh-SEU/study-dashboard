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
class DeployConfig:
    provider: str
    public_url: str
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


def print_access_entries(deploy: DeployConfig) -> None:
    print("")
    print("Access:")
    if deploy.public_url:
        print(f"  Public URL: {deploy.public_url}")
    else:
        print("  Public URL: not configured")


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
        ("计划", "#/plan", "plan.md"),
        ("数学", "#/math", "math.md"),
        ("专业", "#/major", "major.md"),
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
        ("计划", "#/plan", "plan"),
        ("数学", "#/math", "math"),
        ("专业", "#/major", "major"),
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


def problem_section_anchor(target: str, date: str, problem: str | None = None) -> str:
    stem = Path(target).stem.lower()
    date_part = docsify_anchor_id(date)
    if problem is None:
        return f"{stem}-{date_part}"
    number_match = re.search(r"\d+", problem)
    problem_part = number_match.group(0).zfill(2) if number_match else docsify_anchor_id(problem)
    return f"{stem}-{date_part}-{problem_part}"


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
    deploy = DeployConfig(
        provider=str(deploy_raw.get("provider", "github_pages")).strip() or "github_pages",
        public_url=public_url,
        root_directory=str(deploy_raw.get("root_directory", "")).strip(),
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


def strip_plan_overview(content: str) -> str:
    lines = content.lstrip().splitlines()
    if not lines:
        return content
    if not re.match(r"^#\s+.*今日复习计划", lines[0].strip()):
        return content
    for index, line in enumerate(lines[1:], start=1):
        if re.match(r"^##\s+", line):
            return "\n".join(lines[index:]).lstrip() + ("\n" if content.endswith("\n") else "")
    return "\n".join(lines[1:]).lstrip() + ("\n" if content.endswith("\n") else "")


def build_document_markdown(
    document: PublishedDocument,
    published_at: str,
    documents: list[PublishedDocument] | None = None,
) -> str:
    content = strip_duplicate_title(document.content, document.title)
    if Path(document.target).stem.lower() == "plan":
        content = strip_plan_overview(content)
    content = add_document_heading_anchors(document, content).strip()
    parts = [
        f"# {document.title}",
        "",
        document_nav(document.target),
        "",
        '<div class="publish-meta">',
        f"  <span>更新：{published_at}</span>",
        "</div>",
    ]

    if Path(document.target).stem.lower() == "plan" and documents is not None:
        parts.extend(["", build_plan_summary(documents)])

    parts.extend(["", content, ""])
    return "\n".join(parts)


def plan_section_anchor(section_index: int, item_index: int | None = None) -> str:
    if item_index is None:
        return f"plan-section-{section_index:02d}"
    return f"plan-section-{section_index:02d}-{item_index:02d}"


def add_document_heading_anchors(document: PublishedDocument, content: str) -> str:
    stem = Path(document.target).stem.lower()
    if stem == "plan":
        lines: list[str] = []
        section_index = 0
        item_index = 0
        for line in content.splitlines():
            section_match = re.match(r"^##\s+(.+?)\s*$", line)
            if section_match:
                section_index += 1
                item_index = 0
                lines.append(f'<a id="{plan_section_anchor(section_index)}" class="section-anchor"></a>')
                lines.append(line)
                continue

            item_match = re.match(r"^###\s+(.+?)\s*$", line)
            if item_match:
                if section_index == 0:
                    section_index = 1
                    lines.append(f'<a id="{plan_section_anchor(section_index)}" class="section-anchor"></a>')
                item_index += 1
                lines.append(f'<a id="{plan_section_anchor(section_index, item_index)}" class="section-anchor"></a>')
                lines.append(line)
                continue

            lines.append(line)
        return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    if stem not in {"math", "major"}:
        return content

    lines: list[str] = []
    current_date: str | None = None
    for line in content.splitlines():
        date_match = re.match(r"^##\s+(.+?)\s*$", line)
        if date_match:
            title = strip_markdown_marks(date_match.group(1))
            if re.search(r"\d{1,2}[-/.]\d{1,2}", title):
                current_date = title
                lines.append(f'<a id="{problem_section_anchor(document.target, title)}" class="section-anchor"></a>')
            lines.append(line)
            continue

        problem_match = re.match(r"^###\s+(.+?)\s*$", line)
        if problem_match and current_date:
            title = strip_markdown_marks(problem_match.group(1))
            lines.append(f'<a id="{problem_section_anchor(document.target, current_date, title)}" class="section-anchor"></a>')
            lines.append(line)
            continue

        lines.append(line)

    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def extract_plan_sections(document: PublishedDocument) -> list[tuple[str, str, list[tuple[str, str]]]]:
    content = strip_plan_overview(strip_duplicate_title(document.content, document.title))
    if Path(document.target).stem.lower() != "plan":
        return []

    sections: list[tuple[str, str, list[tuple[str, str]]]] = []
    section_index = 0
    item_index = 0
    for line in content.splitlines():
        section_match = re.match(r"^##\s+(.+?)\s*$", line)
        if section_match:
            section_index += 1
            item_index = 0
            title = strip_markdown_marks(section_match.group(1))
            sections.append((title, plan_section_anchor(section_index), []))
            continue

        item_match = re.match(r"^###\s+(.+?)\s*$", line)
        if item_match:
            if not sections:
                section_index = 1
                sections.append(("今日计划", plan_section_anchor(section_index), []))
            item_index += 1
            title = strip_markdown_marks(item_match.group(1))
            sections[-1][2].append((title, plan_section_anchor(section_index, item_index)))

    return sections


def extract_problem_sections(document: PublishedDocument) -> list[tuple[str, str, list[tuple[str, str]]]]:
    content = strip_duplicate_title(document.content, document.title)
    if Path(document.target).stem.lower() not in {"math", "major"}:
        return []

    sections: list[tuple[str, str, list[tuple[str, str]]]] = []
    for line in content.splitlines():
        date_match = re.match(r"^##\s+(.+?)\s*$", line)
        if date_match:
            title = strip_markdown_marks(date_match.group(1))
            if re.search(r"\d{1,2}[-/.]\d{1,2}", title):
                sections.append((title, problem_section_anchor(document.target, title), []))
            continue

        problem_match = re.match(r"^###\s+(.+?)\s*$", line)
        if problem_match:
            title = strip_markdown_marks(problem_match.group(1))
            if not sections:
                sections.append(("本页", problem_section_anchor(document.target, "本页"), []))
            date = sections[-1][0]
            sections[-1][2].append((title, problem_section_anchor(document.target, date, title)))

    return [(date, date_anchor, items) for date, date_anchor, items in sections if items]


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
    return f"""# {site.title}

<p class="home-updated">正在进入今日复习计划...</p>

<p><a href="#/plan">进入今日复习计划</a></p>
"""


def build_sidebar(documents: list[PublishedDocument]) -> str:
    ordered_documents = sorted(documents, key=document_priority)
    lines: list[str] = []
    for document in ordered_documents:
        if Path(document.target).stem.lower() == "plan":
            continue
        route = docsify_route(document.target)
        safe_label = html.escape(document_route_label(document), quote=True)
        lines.append(f'- <a href="{route}" class="toc-subject-link">{safe_label}</a>')
        for date, date_anchor, problems in extract_problem_sections(document):
            safe_date = html.escape(date, quote=True)
            lines.append(
                f'  - <span class="toc-date-row">'
                f'<button type="button" class="toc-toggle" data-toggle-anchor="{date_anchor}" '
                f'aria-label="展开或收起 {safe_date}">›</button>'
                f'<a href="{route}" data-anchor="{date_anchor}" '
                f'class="toc-date-link">{safe_date}</a></span>'
            )
            for problem, anchor in problems:
                safe_problem = html.escape(problem, quote=True)
                lines.append(
                    f'    - <a href="{route}" data-anchor="{anchor}" '
                    f'class="toc-problem-link">{safe_problem}</a>'
                )
    return "\n".join(lines) + "\n"


def build_mobile_drawer(documents: list[PublishedDocument]) -> str:
    sections_html: list[str] = []
    for document in sorted(documents, key=document_priority):
        stem = Path(document.target).stem.lower()
        if stem == "plan":
            sections = extract_plan_sections(document)
        elif stem in {"math", "major"}:
            sections = extract_problem_sections(document)
        else:
            continue
        route = docsify_route(document.target)
        label = html.escape(document_route_label(document))
        date_blocks: list[str] = []
        for date, date_anchor, problems in sections:
            problem_links = "".join(
                f'<a class="study-drawer-problem-link" href="{route}" '
                f'data-route="{route}" data-anchor="{html.escape(anchor, quote=True)}">'
                f'{html.escape(problem)}</a>'
                for problem, anchor in problems
            )
            date_blocks.append(
                f'<div class="study-drawer-date" data-date-anchor="{html.escape(date_anchor, quote=True)}">'
                f'<button class="study-drawer-date-toggle" type="button" '
                f'data-toggle-anchor="{html.escape(date_anchor, quote=True)}" aria-expanded="false">'
                f'<span class="study-drawer-chevron">›</span><span>{html.escape(date)}</span>'
                f'</button>'
                f'<div class="study-drawer-problems" hidden>{problem_links}</div>'
                f'</div>'
            )
        sections_html.append(
            f'<section class="study-drawer-subject" data-route="{route}" hidden>'
            f'<a class="study-drawer-subject-link" href="{route}" data-route="{route}">{label}</a>'
            f'<div class="study-drawer-dates">{"".join(date_blocks)}</div>'
            f'</section>'
        )

    return (
        '<button class="study-drawer-button" type="button" aria-label="打开当前页目录" '
        'aria-controls="study-drawer" aria-expanded="false">'
        '<span></span><span></span><span></span>'
        '</button>'
        '<div class="study-drawer-backdrop" hidden></div>'
        '<aside id="study-drawer" class="study-drawer" aria-label="当前页目录" aria-hidden="true">'
        '<div class="study-drawer-header"><strong>当前页目录</strong>'
        '<button class="study-drawer-close" type="button" aria-label="关闭目录">×</button>'
        '</div><nav class="study-drawer-nav">'
        + "".join(sections_html)
        + '</nav></aside>'
    )


def build_index(site: SiteConfig, documents: list[PublishedDocument]) -> str:
    title = html.escape(site.title)
    description = html.escape(site.description)
    sidebar_title = "复习目录"
    js_title = json.dumps(sidebar_title, ensure_ascii=False)
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
    {build_mobile_drawer(documents)}
    <script>
      if (!window.location.hash || window.location.hash === "#" || window.location.hash === "#/") {{
        window.location.replace("#/plan");
      }}
      window.$docsify = {{
        name: {js_title},
        homepage: "plan.md",
        loadSidebar: true,
        subMaxLevel: 0,
        auto2top: false,
        search: {{
          maxAge: 86400000,
          paths: "auto",
          placeholder: "搜索错题、知识点、计划...",
          noData: "没有找到相关内容",
          depth: 4
        }},
        plugins: [
          function (hook) {{
            hook.doneEach(function () {{
              refreshStudyNavigation();
            }});
          }}
        ]
      }};
      function updateBottomNav() {{
        var hash = window.location.hash || "#/";
        var route = hash.indexOf("#/plan") === 0 ? "plan" :
          hash.indexOf("#/math") === 0 ? "math" :
          hash.indexOf("#/major") === 0 ? "major" : "plan";
        document.querySelectorAll(".mobile-bottom-nav-link").forEach(function (item) {{
          item.classList.toggle("active", item.dataset.route === route);
        }});
      }}
      window.studyPendingAnchor = "";
      function normalizeRoute(route) {{
        return (!route || route === "#" || route === "#/") ? "#/plan" : route;
      }}
      function currentRoute() {{
        return normalizeRoute((window.location.hash || "#/plan").split("?")[0] || "#/plan");
      }}
      window.studyLastRoute = currentRoute();
      function routeFromHref(href) {{
        return normalizeRoute((href || "#/plan").split("?")[0] || "#/plan");
      }}
      function targetIdFromHash() {{
        var hash = window.location.hash || "";
        var match = hash.match(/[?&]id=([^&]+)/);
        return match ? decodeURIComponent(match[1]) : "";
      }}
      function dateAnchorFromAnchor(anchor) {{
        var planMatch = (anchor || "").match(/^(plan-section-\\d{{2}})/);
        if (planMatch) {{
          return planMatch[1];
        }}
        var match = (anchor || "").match(/^(math|major)-(\\d{{1,2}}[-/.]\\d{{1,2}})/);
        return match ? match[1] + "-" + match[2].replace(/[/.]/g, "-") : "";
      }}
      function readOpenDates() {{
        try {{
          return JSON.parse(sessionStorage.getItem("study-dashboard-drawer-open-dates") || "[]");
        }} catch (error) {{
          return [];
        }}
      }}
      function writeOpenDates(dates) {{
        sessionStorage.setItem("study-dashboard-drawer-open-dates", JSON.stringify(Array.from(new Set(dates))));
      }}
      function rememberOpenDate(anchor) {{
        if (!anchor) {{
          return;
        }}
        var dates = readOpenDates();
        if (dates.indexOf(anchor) === -1) {{
          dates.push(anchor);
          writeOpenDates(dates);
        }}
      }}
      function forgetOpenDate(anchor) {{
        writeOpenDates(readOpenDates().filter(function (item) {{
          return item !== anchor;
        }}));
      }}
      function setPendingAnchor(anchor) {{
        if (!anchor) {{
          return;
        }}
        window.studyPendingAnchor = anchor;
        sessionStorage.setItem("study-dashboard-anchor", anchor);
        sessionStorage.setItem("study-dashboard-current-anchor", anchor);
        var dateAnchor = dateAnchorFromAnchor(anchor);
        if (dateAnchor) {{
          rememberOpenDate(dateAnchor);
        }}
      }}
      function readPendingAnchor() {{
        return window.studyPendingAnchor ||
          sessionStorage.getItem("study-dashboard-anchor") ||
          targetIdFromHash();
      }}
      function smoothScrollTopIfNeeded() {{
        if (readPendingAnchor()) {{
          return;
        }}
        var route = currentRoute();
        if (route !== window.studyLastRoute) {{
          window.studyLastRoute = route;
          window.scrollTo({{ top: 0, behavior: "auto" }});
        }}
      }}
      function keepMobileSidebarOpen() {{
        if (window.innerWidth > 768) {{
          return;
        }}
        document.body.classList.add("study-sidebar-locked");
        document.body.classList.remove("close");
      }}
      function getDirectChildUl(item) {{
        for (var i = 0; i < item.children.length; i += 1) {{
          if (item.children[i].tagName === "UL") {{
            return item.children[i];
          }}
        }}
        return null;
      }}
      function getDirectChildLink(item) {{
        return item.querySelector(
          ":scope > a, :scope > .toc-date-row > a, :scope > p > a, :scope > p > .toc-date-row > a"
        );
      }}
      function getDirectToggle(item) {{
        return item.querySelector(
          ":scope > .toc-date-row > .toc-toggle, :scope > p > .toc-date-row > .toc-toggle"
        );
      }}
      function sidebarDepth(item, root) {{
        var depth = 0;
        var node = item;
        while (node && node !== root) {{
          if (node.tagName === "LI") {{
            depth += 1;
          }}
          node = node.parentElement;
        }}
        return depth;
      }}
      function scrollToAnchorWithRetry(anchor, attempt) {{
        if (!anchor) {{
          return;
        }}
        var tries = attempt || 0;
        var target = document.getElementById(anchor);
        if (target) {{
          target.scrollIntoView({{ block: "start", behavior: "auto" }});
          sessionStorage.removeItem("study-dashboard-anchor");
          sessionStorage.setItem("study-dashboard-current-anchor", anchor);
          window.studyPendingAnchor = "";
          [90, 220, 420].forEach(function (delay) {{
            window.setTimeout(function () {{
              var stableTarget = document.getElementById(anchor);
              if (stableTarget) {{
                stableTarget.scrollIntoView({{ block: "start", behavior: "auto" }});
              }}
            }}, delay);
          }});
          window.setTimeout(enhanceSidebar, 30);
          return;
        }}
        if (tries < 40) {{
          window.setTimeout(function () {{
            scrollToAnchorWithRetry(anchor, tries + 1);
          }}, 80);
        }}
      }}
      function scrollPendingAnchor() {{
        scrollToAnchorWithRetry(readPendingAnchor(), 0);
      }}
      function drawerElements() {{
        return {{
          drawer: document.getElementById("study-drawer"),
          backdrop: document.querySelector(".study-drawer-backdrop"),
          button: document.querySelector(".study-drawer-button")
        }};
      }}
      function openStudyDrawer() {{
        var parts = drawerElements();
        if (!parts.drawer || !parts.backdrop || !parts.button) {{
          return;
        }}
        document.body.classList.add("study-drawer-open");
        parts.drawer.setAttribute("aria-hidden", "false");
        parts.button.setAttribute("aria-expanded", "true");
        parts.backdrop.hidden = false;
        syncStudyDrawer();
      }}
      function closeStudyDrawer() {{
        var parts = drawerElements();
        document.body.classList.remove("study-drawer-open");
        if (parts.drawer) {{
          parts.drawer.setAttribute("aria-hidden", "true");
        }}
        if (parts.button) {{
          parts.button.setAttribute("aria-expanded", "false");
        }}
        if (parts.backdrop) {{
          parts.backdrop.hidden = true;
        }}
      }}
      function setDrawerDateOpen(dateBlock, open) {{
        if (!dateBlock) {{
          return;
        }}
        var panel = dateBlock.querySelector(".study-drawer-problems");
        var button = dateBlock.querySelector(".study-drawer-date-toggle");
        dateBlock.classList.toggle("is-open", open);
        if (panel) {{
          panel.hidden = !open;
        }}
        if (button) {{
          button.setAttribute("aria-expanded", open ? "true" : "false");
        }}
        var anchor = dateBlock.dataset.dateAnchor || "";
        if (open) {{
          rememberOpenDate(anchor);
        }} else {{
          forgetOpenDate(anchor);
        }}
      }}
      function syncStudyDrawer() {{
        var drawer = document.getElementById("study-drawer");
        if (!drawer) {{
          return;
        }}
        var route = currentRoute();
        var targetId = readPendingAnchor() ||
          sessionStorage.getItem("study-dashboard-current-anchor") ||
          targetIdFromHash();
        var openDates = readOpenDates();
        var currentDate = dateAnchorFromAnchor(targetId);
        if (currentDate && openDates.indexOf(currentDate) === -1) {{
          openDates.push(currentDate);
          writeOpenDates(openDates);
        }}
        drawer.querySelectorAll(".study-drawer-subject").forEach(function (subject) {{
          var isCurrent = subject.dataset.route === route;
          subject.hidden = !isCurrent;
          subject.classList.toggle("is-current", isCurrent);
        }});
        drawer.querySelectorAll(".study-drawer-date").forEach(function (dateBlock) {{
          var anchor = dateBlock.dataset.dateAnchor || "";
          setDrawerDateOpen(dateBlock, openDates.indexOf(anchor) !== -1);
          dateBlock.classList.toggle("is-current", targetId === anchor || targetId.indexOf(anchor + "-") === 0);
        }});
        drawer.querySelectorAll(".study-drawer-problem-link").forEach(function (link) {{
          link.classList.toggle("is-current", targetId === link.dataset.anchor);
        }});
      }}
      function enhanceSidebar() {{
        var sidebar = document.querySelector(".sidebar");
        if (!sidebar) {{
          return;
        }}
        var targetId = readPendingAnchor() ||
          sessionStorage.getItem("study-dashboard-current-anchor") ||
          targetIdFromHash();
        var openDates = readOpenDates();
        var currentDate = dateAnchorFromAnchor(targetId);
        if (currentDate && openDates.indexOf(currentDate) === -1) {{
          openDates.push(currentDate);
          writeOpenDates(openDates);
        }}
        sidebar.querySelectorAll("li").forEach(function (item) {{
          var childUl = getDirectChildUl(item);
          var link = getDirectChildLink(item);
          var toggle = getDirectToggle(item);
          var depth = sidebarDepth(item, sidebar);
          item.classList.remove("nav-current");
          if (childUl) {{
            item.classList.add("nav-collapsible");
            if (depth <= 1) {{
              item.classList.add("nav-open");
            }}
            if (link && link.dataset.anchor && link.classList.contains("toc-date-link")) {{
              item.classList.add("nav-date");
              if (toggle) {{
                toggle.setAttribute("aria-expanded", "false");
              }}
              if (
                openDates.indexOf(link.dataset.anchor) !== -1 ||
                targetId === link.dataset.anchor ||
                targetId.indexOf(link.dataset.anchor + "-") === 0
              ) {{
                item.classList.add("nav-open");
                if (toggle) {{
                  toggle.setAttribute("aria-expanded", "true");
                }}
              }} else {{
                item.classList.remove("nav-open");
              }}
            }}
          }}
          if (link && link.dataset.anchor && targetId === link.dataset.anchor) {{
            item.classList.add("nav-current");
            var parent = item.parentElement;
            while (parent && parent !== sidebar) {{
              if (parent.tagName === "LI") {{
                parent.classList.add("nav-open");
              }}
              parent = parent.parentElement;
            }}
          }}
        }});
      }}
      document.addEventListener("click", function (event) {{
        var openButton = event.target.closest(".study-drawer-button");
        if (!openButton) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        openStudyDrawer();
      }}, true);
      document.addEventListener("click", function (event) {{
        if (!event.target.closest(".study-drawer-close") && !event.target.closest(".study-drawer-backdrop")) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        closeStudyDrawer();
      }}, true);
      document.addEventListener("click", function (event) {{
        var dateButton = event.target.closest(".study-drawer-date-toggle");
        if (!dateButton) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        var dateBlock = dateButton.closest(".study-drawer-date");
        setDrawerDateOpen(dateBlock, !(dateBlock && dateBlock.classList.contains("is-open")));
      }}, true);
      document.addEventListener("click", function (event) {{
        var problemLink = event.target.closest(".study-drawer-problem-link");
        if (!problemLink) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        var anchor = problemLink.dataset.anchor || "";
        var route = routeFromHref(problemLink.getAttribute("href"));
        setPendingAnchor(anchor);
        syncStudyDrawer();
        if (route === currentRoute()) {{
          window.setTimeout(scrollPendingAnchor, 0);
        }} else {{
          window.location.hash = route.replace(/^#/, "");
        }}
      }}, true);
      document.addEventListener("click", function (event) {{
        var subjectLink = event.target.closest(".study-drawer-subject-link");
        if (!subjectLink) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        sessionStorage.removeItem("study-dashboard-anchor");
        window.studyPendingAnchor = "";
        var route = routeFromHref(subjectLink.getAttribute("href"));
        if (route === currentRoute()) {{
          window.setTimeout(function () {{
            window.scrollTo({{ top: 0, behavior: "auto" }});
          }}, 0);
        }} else {{
          window.location.hash = route.replace(/^#/, "");
        }}
      }}, true);
      function toggleDateItem(toggle) {{
        var item = toggle.closest("li");
        if (!item) {{
          return;
        }}
        item.classList.toggle("nav-open");
        var anchor = toggle.dataset.toggleAnchor || "";
        if (item.classList.contains("nav-open")) {{
          rememberOpenDate(anchor);
          toggle.setAttribute("aria-expanded", "true");
        }} else {{
          forgetOpenDate(anchor);
          toggle.setAttribute("aria-expanded", "false");
        }}
      }}
      function handleSidebarToggle(event) {{
        var toggle = event.target.closest(".sidebar .toc-toggle");
        if (!toggle) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        keepMobileSidebarOpen();

        if (event.type === "pointerdown" || event.type === "touchstart") {{
          return;
        }}

        var now = Date.now();
        if (now - window.studyLastToggleAt < 260) {{
          return;
        }}
        window.studyLastToggleAt = now;
        toggleDateItem(toggle);
      }}
      ["pointerdown", "pointerup", "touchstart", "touchend", "click"].forEach(function (eventName) {{
        document.addEventListener(eventName, handleSidebarToggle, true);
      }});
      document.addEventListener("click", function (event) {{
        if (!event.target.closest(".sidebar-toggle")) {{
          return;
        }}
        document.body.classList.remove("study-sidebar-locked");
      }}, true);
      document.addEventListener("click", function (event) {{
        var link = event.target.closest(".sidebar a[data-anchor]");
        if (!link) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        var anchor = link.dataset.anchor || "";
        setPendingAnchor(anchor);
        keepMobileSidebarOpen();
        var item = link.closest("li");
        if (item && link.classList.contains("toc-date-link")) {{
          item.classList.add("nav-open");
        }}
        var route = routeFromHref(link.getAttribute("href"));
        if (route === currentRoute()) {{
          window.setTimeout(scrollPendingAnchor, 0);
        }} else {{
          window.location.hash = route.replace(/^#/, "");
        }}
      }}, true);
      document.addEventListener("click", function (event) {{
        var navLink = event.target.closest(".sidebar .toc-subject-link");
        if (!navLink) {{
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        sessionStorage.removeItem("study-dashboard-anchor");
        window.studyPendingAnchor = "";
        keepMobileSidebarOpen();
        var route = routeFromHref(navLink.getAttribute("href"));
        if (route === currentRoute()) {{
          window.setTimeout(function () {{
            window.scrollTo({{ top: 0, behavior: "auto" }});
          }}, 0);
        }} else {{
          window.location.hash = route.replace(/^#/, "");
        }}
      }}, true);
      document.addEventListener("click", function (event) {{
        var navLink = event.target.closest(".mobile-bottom-nav-link");
        if (!navLink) {{
          return;
        }}
        sessionStorage.removeItem("study-dashboard-anchor");
        window.studyPendingAnchor = "";
        document.body.classList.remove("study-sidebar-locked");
        closeStudyDrawer();
        window.setTimeout(updateBottomNav, 0);
      }});
      function refreshStudyNavigation() {{
        updateBottomNav();
        window.setTimeout(function () {{
          enhanceSidebar();
          syncStudyDrawer();
          if (readPendingAnchor()) {{
            scrollPendingAnchor();
          }} else {{
            smoothScrollTopIfNeeded();
          }}
        }}, 120);
      }}
      window.addEventListener("hashchange", refreshStudyNavigation);
      window.addEventListener("DOMContentLoaded", refreshStudyNavigation);
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
  font-size: 1.18rem;
  font-weight: 800;
}

.sidebar {
  border-right: 1px solid var(--line-soft);
  background: #fff;
}

.sidebar ul {
  padding-left: 18px;
}

.sidebar ul li {
  margin: 2px 0;
}

.sidebar ul li p {
  margin: 0;
}

.sidebar ul li a {
  color: #39413b;
  line-height: 1.55;
  text-decoration: none;
}

.sidebar > ul > li > a {
  color: #1d342f;
  font-weight: 700;
}

.sidebar ul li ul li > a {
  color: #1d564c;
  font-weight: 650;
}

.sidebar ul li ul li ul li > a {
  color: #39413b;
  font-weight: 500;
}

.sidebar ul li.active > a {
  color: #1d7a68;
  border-right: 0 !important;
  font-weight: 700;
}

.sidebar li.nav-date > a {
  display: none;
}

.sidebar .toc-date-row {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
}

.sidebar .toc-toggle {
  display: inline-flex;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  color: #7d8982;
  background: transparent;
  font: inherit;
  font-size: 1.05rem;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease, transform 0.12s ease;
}

.sidebar .toc-toggle:hover,
.sidebar .toc-toggle:focus-visible {
  color: #1d7a68;
  background: #eef6f3;
  outline: none;
}

.sidebar li.nav-date.nav-open > .toc-date-row .toc-toggle,
.sidebar li.nav-date.nav-open > p > .toc-date-row .toc-toggle {
  transform: rotate(90deg);
}

.sidebar .toc-date-link {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding-right: 6px;
}

.sidebar .toc-problem-link,
.sidebar .toc-subject-link {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
}

.sidebar li.nav-date:not(.nav-open) > ul {
  display: none;
}

.sidebar li.nav-current > a {
  color: #1d7a68;
  font-weight: 700;
}

.section-anchor {
  display: block;
  position: relative;
  top: -18px;
  height: 0;
  overflow: hidden;
}

.content {
  padding-top: 12px;
}

.mobile-bottom-nav {
  display: none;
}

.study-drawer-button,
.study-drawer,
.study-drawer-backdrop {
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
  margin-bottom: 0.72rem;
}

.markdown-section h2 {
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: 0.36rem;
  font-size: 1.45rem;
  margin-top: 1.45rem;
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
  margin: 0 0.42em 0.16em -1.15em;
  vertical-align: middle;
  accent-color: #1d7a68;
}

.markdown-section li:has(input[type="checkbox"]) {
  list-style: none;
  margin: 0.12rem 0 0.12rem 0.12rem;
  padding: 0.04rem 0.16rem;
  border-radius: 6px;
}

.markdown-section li:has(input[type="checkbox"]:checked) {
  color: #5f6963;
  background: transparent;
}

.publish-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 6px;
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

.markdown-section .publish-meta + h1,
.markdown-section .publish-meta + h2,
.markdown-section .publish-meta + .section-anchor + h1,
.markdown-section .publish-meta + .section-anchor + h2 {
  margin-top: 8px !important;
}

.markdown-section .publish-meta ~ .section-anchor:first-of-type + h1,
.markdown-section .publish-meta ~ .section-anchor:first-of-type + h2 {
  margin-top: 8px !important;
}

.markdown-section .publish-meta + .today-summary {
  margin-top: 8px;
}

.markdown-section .today-summary + h1,
.markdown-section .today-summary + h2,
.markdown-section .today-summary + .section-anchor + h1,
.markdown-section .today-summary + .section-anchor + h2 {
  margin-top: 14px !important;
}

.markdown-section .publish-meta + .section-anchor {
  margin: 0;
  padding: 0;
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
    padding: 16px 14px 92px;
    font-size: 16px;
    line-height: 1.76;
  }

  .markdown-section h1 {
    font-size: 1.48rem;
    line-height: 1.25;
    margin: 0 0 0.42rem !important;
  }

  .markdown-section h2 {
    font-size: 1.22rem;
    margin-top: 1rem;
  }

  .markdown-section .publish-meta + h1,
  .markdown-section .publish-meta + h2,
  .markdown-section .publish-meta + .section-anchor + h1,
  .markdown-section .publish-meta + .section-anchor + h2,
  .markdown-section .publish-meta ~ .section-anchor:first-of-type + h1,
  .markdown-section .publish-meta ~ .section-anchor:first-of-type + h2 {
    margin-top: 0.38rem !important;
  }

  .markdown-section .publish-meta + .today-summary {
    margin-top: 8px;
  }

  .markdown-section .today-summary + h1,
  .markdown-section .today-summary + h2,
  .markdown-section .today-summary + .section-anchor + h1,
  .markdown-section .today-summary + .section-anchor + h2 {
    margin-top: 0.65rem !important;
  }

  .markdown-section .publish-meta + .section-anchor {
    margin: 0;
    padding: 0;
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

  .sidebar,
  .sidebar-toggle {
    display: none !important;
  }

  .content,
  body.close .content {
    left: 0 !important;
    transform: none !important;
  }

  .study-drawer-button {
    position: fixed;
    left: 12px;
    bottom: max(12px, env(safe-area-inset-bottom));
    z-index: 80;
    display: inline-flex;
    width: 44px;
    height: 44px;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 4px;
    border: 1px solid rgba(29, 122, 104, 0.16);
    border-radius: 14px;
    color: #1d7a68;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 5px 16px rgba(24, 47, 40, 0.1);
    backdrop-filter: blur(8px);
  }

  .study-drawer-button span {
    width: 17px;
    height: 2px;
    border-radius: 999px;
    background: currentColor;
  }

  .study-drawer-backdrop {
    position: fixed;
    inset: 0;
    z-index: 68;
    display: block;
    background: rgba(20, 28, 24, 0.26);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.16s ease;
  }

  .study-drawer-backdrop[hidden] {
    display: none;
  }

  .study-drawer {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 75;
    display: flex;
    width: min(82vw, 320px);
    max-width: 320px;
    flex-direction: column;
    border-right: 1px solid var(--line-soft);
    background: #fff;
    box-shadow: 10px 0 28px rgba(24, 47, 40, 0.12);
    transform: translateX(-102%);
    transition: transform 0.18s ease;
  }

  body.study-drawer-open .study-drawer {
    transform: translateX(0);
  }

  body.study-drawer-open .study-drawer-backdrop {
    opacity: 1;
    pointer-events: auto;
  }

  .study-drawer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 22px 18px 12px;
    color: #20362f;
  }

  .study-drawer-header strong {
    font-size: 1.12rem;
    font-weight: 800;
  }

  .study-drawer-close {
    width: 34px;
    height: 34px;
    border: 0;
    border-radius: 999px;
    color: #52605a;
    background: #f2f6f3;
    font-size: 1.25rem;
    line-height: 1;
  }

  .study-drawer-nav {
    flex: 1;
    overflow-y: auto;
    padding: 4px 18px 86px;
    -webkit-overflow-scrolling: touch;
  }

  .study-drawer-subject {
    margin: 10px 0 14px;
  }

  .study-drawer-subject-link {
    display: inline-flex;
    min-height: 34px;
    align-items: center;
    color: #1d342f;
    font-weight: 760;
    text-decoration: none;
  }

  .study-drawer-subject.is-current > .study-drawer-subject-link {
    color: #1d7a68;
  }

  .study-drawer-date {
    margin: 2px 0 4px;
  }

  .study-drawer-date-toggle {
    display: inline-flex;
    min-height: 34px;
    align-items: center;
    gap: 7px;
    border: 0;
    border-radius: 8px;
    padding: 2px 8px 2px 0;
    color: #1d564c;
    background: transparent;
    font: inherit;
    font-weight: 760;
  }

  .study-drawer-chevron {
    display: inline-flex;
    width: 26px;
    height: 26px;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    color: #7d8982;
    transition: transform 0.12s ease, background-color 0.12s ease;
  }

  .study-drawer-date-toggle:active .study-drawer-chevron {
    background: #eef6f3;
  }

  .study-drawer-date.is-open .study-drawer-chevron {
    color: #1d7a68;
    transform: rotate(90deg);
  }

  .study-drawer-date.is-current .study-drawer-date-toggle {
    color: #0f5f52;
    background: #eef7f3;
  }

  .study-drawer-problems {
    display: grid;
    gap: 2px;
    margin: 0 0 8px 34px;
  }

  .study-drawer-problems[hidden] {
    display: none !important;
  }

  .study-drawer-problem-link {
    position: relative;
    display: inline-flex;
    min-height: 30px;
    align-items: center;
    border-radius: 8px;
    padding: 2px 8px;
    color: #39413b;
    font-weight: 520;
    text-decoration: none;
  }

  .study-drawer-problem-link.is-current {
    color: #0f5f52;
    background: #eef7f3;
    font-weight: 760;
  }

  .study-drawer-problem-link.is-current::before {
    width: 3px;
    align-self: stretch;
    border-radius: 999px;
    margin: 3px 8px 3px 0;
    background: #1d7a68;
    content: "";
  }

  .sidebar ul {
    padding-left: 14px;
  }

  .sidebar ul li {
    margin: 1px 0;
  }

  .sidebar ul li a {
    line-height: 1.45;
  }

  .sidebar .toc-date-row {
    min-height: 32px;
  }

  .sidebar .toc-toggle {
    width: 34px;
    height: 32px;
    flex-basis: 34px;
    border-radius: 9px;
  }

  .sidebar .toc-date-link {
    min-height: 32px;
  }

  .sidebar .toc-problem-link,
  .sidebar .toc-subject-link {
    min-height: 30px;
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
    margin: 0 0 6px;
    font-size: 0.78rem;
  }

  .publish-meta span {
    display: inline-block;
    max-width: 100%;
    margin-bottom: 0;
    border-radius: 6px;
    padding: 3px 6px;
    overflow-wrap: anywhere;
  }

  .mobile-bottom-nav {
    position: fixed;
    right: 12px;
    bottom: max(9px, env(safe-area-inset-bottom));
    left: 74px;
    z-index: 35;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1px;
    border: 1px solid rgba(29, 122, 104, 0.16);
    border-radius: 14px;
    padding: 3px;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 5px 16px rgba(24, 47, 40, 0.1);
    backdrop-filter: blur(8px);
  }

  .mobile-bottom-nav-link {
    position: relative;
    display: flex;
    min-height: 38px;
    align-items: center;
    justify-content: center;
    border-radius: 11px;
    padding: 3px 2px 5px;
    color: #1d564c;
    font-size: 0.82rem;
    font-weight: 750;
    line-height: 1;
    text-align: center;
    text-decoration: none;
    white-space: nowrap;
  }

  .mobile-bottom-nav-link.active {
    color: #1d7a68;
    background: #f6fbf8;
  }

  .mobile-bottom-nav-link.active::after {
    position: absolute;
    right: 30%;
    bottom: 2px;
    left: 30%;
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
        (site.output_dir / document.target).write_text(
            build_document_markdown(output_document, published_at, documents),
            encoding="utf-8",
        )

    (site.output_dir / "README.md").write_text(build_home(site, documents, published_at), encoding="utf-8")
    (site.output_dir / "_sidebar.md").write_text(build_sidebar(documents), encoding="utf-8")
    (site.output_dir / "index.html").write_text(build_index(site, documents), encoding="utf-8")
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

    if deploy.public_url and not is_http_url(deploy.public_url):
        errors.append(f"Public URL should start with http:// or https://: {deploy.public_url}")

    files = [path for path in output.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)

    print("")
    print("Deploy check")
    print(f"Provider: {deploy.provider}")
    print(f"Public URL: {deploy.public_url or '(not configured)'}")
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

    print("[6/6] GitHub Pages URL and routes")
    if deploy is None:
        errors.append("Cannot check deploy.public_url because config failed.")
    else:
        if deploy.public_url:
            print(f"      Public URL: {deploy.public_url}")
            if not is_http_url(deploy.public_url):
                errors.append(f"deploy.public_url should start with http:// or https://: {deploy.public_url}")
        else:
            warnings.append("deploy.public_url is empty. Fill it after GitHub Pages deployment.")

        workflow = PROJECT_DIR / ".github" / "workflows" / "pages.yml"
        if workflow.exists() and workflow.stat().st_size > 0:
            print("      OK GitHub Pages workflow exists.")
        else:
            errors.append("Missing GitHub Pages workflow: .github/workflows/pages.yml")

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
    print("  GitHub Pages:")
    print("    Settings -> Pages: GitHub Actions")
    print(f"    Public URL: {deploy.public_url or '(not configured)'}")
    print("  Privacy:")
    print("    Public repositories or public Pages sites are not suitable for private study notes.")
    if not deploy.public_url:
        print("  Public URL:")
        print("    部署完成后，把 GitHub Pages 网址填入 config.json 的 deploy.public_url。")


def print_cloud_instructions(deploy: DeployConfig) -> None:
    print("")
    print("GitHub Pages deployment instructions")
    print("")
    print("GitHub Pages:")
    print("  1. Push this project to GitHub.")
    print("  2. Keep Settings -> Pages set to GitHub Actions.")
    print("  3. The workflow publishes cloud_site.")
    print("  4. After deployment, use deploy.public_url as the site URL.")


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
    if not deploy.public_url:
        print("deploy.public_url is empty.")
        print("部署完成后，把 GitHub Pages 网址填入 config.json 的 deploy.public_url。")
        return 1
    print(f"Opening public URL: {deploy.public_url}")
    webbrowser.open(deploy.public_url)
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
    parser.add_argument("--open-public", action="store_true", help="Open deploy.public_url from config.json.")
    parser.add_argument("--git", action="store_true", help="Run git add/commit/push after generation.")
    parser.add_argument("--message", default="Update study dashboard", help="Commit message used with --git.")
    parser.add_argument("--yes", action="store_true", help="Skip --git confirmation.")
    parser.add_argument("--clean", action="store_true", help="Clean old generated Markdown and copied media before publishing.")
    args = parser.parse_args()

    try:
        if args.open_public:
            return open_public_url()

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
