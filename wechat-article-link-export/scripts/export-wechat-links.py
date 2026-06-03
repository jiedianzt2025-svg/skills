#!/usr/bin/env python3
"""Export public WeChat Official Account article links to CSV.

This script uses a seed mp.weixin.qq.com article URL, Agent Reach's mcporter
configuration, and public mirror pages when available. It never bypasses login,
CAPTCHA, or access controls.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; wechat-link-export/1.0)"
JINTIANKANSHA = "http://www.jintiankansha.me"


def fetch_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def first_match(patterns: Iterable[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def parse_seed_metadata(seed_url: str) -> dict[str, str]:
    raw = fetch_text(seed_url)
    return {
        "title": first_match(
            [
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                r"var msg_title\s*=\s*'([^']+)'",
                r'var msg_title\s*=\s*htmlDecode\("([^"]+)"\)',
            ],
            raw,
        ),
        "author": first_match(
            [
                r'<meta[^>]+property=["\']og:article:author["\'][^>]+content=["\']([^"\']+)',
                r'var nickname\s*=\s*htmlDecode\("([^"]+)"\)',
            ],
            raw,
        ),
        "nickname": first_match([r'var nickname\s*=\s*htmlDecode\("([^"]+)"\)'], raw),
        "account": first_match([r'var user_name\s*=\s*"([^"]+)"'], raw),
    }


def default_mcporter_config() -> Path:
    home = Path.home()
    return home / ".agent-reach" / "config" / "mcporter.json"


def find_mcporter() -> str:
    command = shutil.which("mcporter") or shutil.which("mcporter.cmd")
    if not command:
        raise RuntimeError("mcporter was not found on PATH. Run scripts/bootstrap-agent-reach.ps1 or configure Agent Reach first.")
    return command


def call_exa_search(query: str, config_path: Path, num_results: int = 100) -> str:
    command = [
        find_mcporter(),
        "--config",
        str(config_path),
        "call",
        "exa.web_search_exa",
        f"query={query}",
        f"numResults={num_results}",
        "--output",
        "json",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Exa search failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return completed.stdout
    chunks: list[str] = []
    for item in payload.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(str(item.get("text", "")))
    return "\n".join(chunks) or completed.stdout


def extract_jintiankansha_article_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://www\.jintiankansha\.me/t/[A-Za-z0-9_-]+", text)
    # preserve order
    return list(dict.fromkeys(urls))


def extract_column_url_from_article(article_url: str) -> str:
    try:
        page = fetch_text(article_url)
    except (HTTPError, URLError, TimeoutError):
        return ""
    matches = re.findall(r'href=["\'](https?://www\.jintiankansha\.me/column/[A-Za-z0-9_-]+|/column/[A-Za-z0-9_-]+)["\']', page)
    if not matches:
        return ""
    return urljoin(JINTIANKANSHA, matches[0])


def discover_column(seed_url: str, metadata: dict[str, str], config_path: Path) -> tuple[str, str]:
    terms = [metadata.get("nickname"), metadata.get("author"), metadata.get("title"), metadata.get("account")]
    useful_terms = " ".join(t for t in terms if t)
    queries = [
        f"微信公众号 {useful_terms} 今天看啥 专栏 历史文章",
        f"site:jintiankansha.me {useful_terms} 微信公众号 历史文章",
        f"site:mp.weixin.qq.com {useful_terms} 微信公众号 文章",
    ]
    transcript_parts: list[str] = []
    for query in queries:
        result_text = call_exa_search(query, config_path)
        transcript_parts.append(f"QUERY: {query}\n{result_text}")
        for article_url in extract_jintiankansha_article_urls(result_text):
            column_url = extract_column_url_from_article(article_url)
            if column_url:
                return column_url, "\n\n".join(transcript_parts)
    return "", "\n\n".join(transcript_parts)


def crawl_column(column_url: str, max_pages: int = 500) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    empty_pages = 0
    column_path = re.search(r"/column/[A-Za-z0-9_-]+", column_url)
    column_marker = column_path.group(0) if column_path else ""

    for page_no in range(1, max_pages + 1):
        page_url = column_url if page_no == 1 else f"{column_url}?page={page_no}"
        try:
            page = fetch_text(page_url)
        except (HTTPError, URLError, TimeoutError):
            empty_pages += 1
            if empty_pages >= 2:
                break
            continue

        new_count = 0
        pattern = re.compile(r'href=["\'](https?://www\.jintiankansha\.me/t/[A-Za-z0-9_-]+|/t/[A-Za-z0-9_-]+)["\'][^>]*>(.*?)</a>', re.S)
        for match in pattern.finditer(page):
            url = urljoin(JINTIANKANSHA, match.group(1))
            article_id = url.rsplit("/", 1)[-1]
            title = clean_text(match.group(2))
            if not title or url in seen:
                continue
            # Keep links from this column. This filters unrelated recommendations on many pages.
            nearby = page[match.end() : match.end() + 800]
            if column_marker and column_marker not in nearby and page_no > 1:
                continue
            seen.add(url)
            rows.append(
                {
                    "标题": title,
                    "链接": url,
                    "链接类型": "公开列表镜像URL",
                    "列表页": str(page_no),
                    "备注": "镜像站原文跳转可能需要登录；未绕过访问控制",
                    "id": article_id,
                }
            )
            new_count += 1

        if new_count == 0:
            empty_pages += 1
        else:
            empty_pages = 0
        print(f"page={page_no} new={new_count} total={len(rows)}", file=sys.stderr)
        if empty_pages >= 2:
            break

    return rows


def write_csv(path: Path, account_name: str, seed_url: str, seed_title: str, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen_links = {seed_url}
    output_rows = [
        {
            "公众号": account_name,
            "标题": seed_title or "种子文章",
            "链接": seed_url,
            "链接类型": "已确认微信原始URL",
            "列表页": "",
            "备注": "用户提供的种子文章",
        }
    ]
    for row in rows:
        link = row["链接"]
        if link in seen_links:
            continue
        seen_links.add(link)
        output_rows.append(
            {
                "公众号": account_name,
                "标题": row["标题"],
                "链接": link,
                "链接类型": row["链接类型"],
                "列表页": row["列表页"],
                "备注": row["备注"],
            }
        )

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["公众号", "标题", "链接", "链接类型", "列表页", "备注"])
        writer.writeheader()
        writer.writerows(output_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public WeChat Official Account article links to CSV.")
    parser.add_argument("seed_url", help="A public mp.weixin.qq.com article URL from the target account.")
    parser.add_argument("--column-url", help="Optional public jintiankansha column URL if auto-discovery fails.")
    parser.add_argument("--output", help="CSV output path. Defaults to ~/.agent-reach/output/<account>_articles.csv")
    parser.add_argument("--config", default=str(default_mcporter_config()), help="mcporter config path")
    args = parser.parse_args()

    if "mp.weixin.qq.com" not in args.seed_url:
        print("The seed URL should be an mp.weixin.qq.com article URL.", file=sys.stderr)

    metadata = parse_seed_metadata(args.seed_url)
    account_name = metadata.get("nickname") or metadata.get("author") or metadata.get("account") or "微信公众号"
    seed_title = metadata.get("title")
    print(f"account={account_name}", file=sys.stderr)
    print(f"seed_title={seed_title}", file=sys.stderr)

    column_url = args.column_url or ""
    if not column_url:
        column_url, transcript = discover_column(args.seed_url, metadata, Path(args.config))
        if not column_url:
            print("Could not auto-discover a public historical column. Search transcript follows:", file=sys.stderr)
            print(transcript, file=sys.stderr)
    if column_url:
        print(f"column_url={column_url}", file=sys.stderr)
        rows = crawl_column(column_url)
    else:
        rows = []

    if args.output:
        output = Path(args.output)
    else:
        safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", account_name).strip("_") or "wechat"
        output = Path.home() / ".agent-reach" / "output" / f"{safe_name}_articles.csv"

    write_csv(output, account_name, args.seed_url, seed_title, rows)
    print(f"csv={output}")
    print(f"rows={len(rows) + 1}")
    print(f"mirror_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
