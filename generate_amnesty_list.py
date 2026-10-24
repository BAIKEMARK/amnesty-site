"""Generate the standalone human amnesty list from Bilibili comment CSVs.

Offline:
    python generate_amnesty_list.py --source comments.csv --output amnesty-site/index.html

Fetch the current visible comments first:
    python generate_amnesty_list.py --fetch --output amnesty-site/index.html
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from bilibili import BilibiliClient, BilibiliError
from comment_batch import filter_comments, normalize_keywords, write_user_summary
from comment_csv import read_reviewed, write_comments
from config import ROOT, Settings


TEMPLATE = ROOT / "templates" / "amnesty_template.html"
DEFAULT_OUTPUT = ROOT / "amnesty-site" / "index.html"
DEFAULT_KEYWORDS = ["赦免"]
EXCLUDED = {"DeepSeek鲸鱼娘在运营", "潜行的大肥鱼"}
MANUAL_ADD = "取重复的昵称太简单了"
NAME_CORRECTIONS = {"芙兰朵露_斯卡雷特": "芺兰朵露_斯卡雷特"}
HIGHLIGHT = {
    "芺兰朵露_斯卡雷特", "两斤鱼-TJFish", "禅雅塔童话之上勾拳",
    "秋塘空传逸鹤声", "不改了就这样_", "想要吃大白饭的大肥鱼", MANUAL_ADD,
}
CHINA_TIME = timezone(timedelta(hours=8))


def parse_comment_time(value: Any) -> datetime | None:
    """Parse the exported wall-clock time; Unix timestamps are treated as UTC."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), CHINA_TIME).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CHINA_TIME).replace(tzinfo=None)
    return parsed


def _build_names_from_matches(selected: Iterable[dict[str, Any]]) -> list[str]:
    first_seen: dict[str, datetime] = {}
    for row in selected:
        raw_name = str(row.get("评论者昵称") or "").strip()
        if not raw_name:
            continue
        name = NAME_CORRECTIONS.get(raw_name, raw_name)
        if name in EXCLUDED:
            continue
        stamp = parse_comment_time(row.get("发表时间")) or datetime.max
        if name not in first_seen or stamp < first_seen[name]:
            first_seen[name] = stamp

    names = sorted(first_seen, key=lambda name: first_seen[name])
    if MANUAL_ADD not in first_seen:
        names.append(MANUAL_ADD)
    return names


def build_names(rows: Iterable[dict[str, Any]], keywords: Iterable[str]) -> list[str]:
    """Filter applicants, deduplicate by nickname, and order by first request."""
    return _build_names_from_matches(filter_comments(rows, keywords))


def latest_comment_time(rows: Iterable[dict[str, Any]]) -> datetime | None:
    stamps = [stamp for row in rows if (stamp := parse_comment_time(row.get("发表时间"))) is not None]
    return max(stamps) if stamps else None


def render_page(
    template: str,
    names: list[str],
    generated_at: datetime | None = None,
    statistics_at: datetime | None = None,
) -> str:
    """Fill the reviewed HTML template with an escaped, numbered name list."""
    generated_at = generated_at or datetime.now(CHINA_TIME)
    statistics_at = statistics_at or generated_at
    items = []
    for number, name in enumerate(names, 1):
        class_name = "person highlighted" if name in HIGHLIGHT else "person"
        items.append(
            f'<li class="{class_name}"><span class="num">{number:03d}</span>'
            f'<span class="name">{html.escape(name, quote=True)}</span></li>'
        )
    replacements = {
        "{{COUNT}}": str(len(names)),
        "{{ITEMS}}": "\n".join(items),
        "{{DATE}}": statistics_at.strftime("%Y-%m-%d"),
    }
    page = template
    for marker, value in replacements.items():
        if marker not in page:
            raise ValueError(f"网页模板缺少占位符 {marker}")
        page = page.replace(marker, value)
    if "{{" in page or "}}" in page:
        raise ValueError("网页模板中仍有未替换的占位符")
    return page


def fetch_comments(settings: Settings) -> list[dict[str, Any]]:
    if not settings.has_bilibili_credentials():
        raise ValueError("在线抓取需要在本地配置 B 站登录 Cookie")
    client = BilibiliClient(settings)

    def progress(channel: str, completed: int, total: int, count: int) -> None:
        print(f"[抓取] {channel} {completed}/{total}，累计 {count} 条评论", flush=True)

    return client.export_owned_comments(progress=progress)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按评论区申请生成独立的人类特赦名单网页")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source", type=Path, help="已有评论 CSV；不联网")
    source.add_argument("--fetch", action="store_true", help="在线抓取账号投稿和动态评论，不读取私信")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"网页输出路径（默认：{DEFAULT_OUTPUT}）")
    parser.add_argument("--template", type=Path, default=TEMPLATE, help=f"HTML 模板路径（默认：{TEMPLATE}）")
    parser.add_argument("--keyword", action="append", default=None, help="申请评论关键词，可重复指定；默认：赦免")
    parser.add_argument("--comments-output", type=Path, help="可选：另存命中评论明细 CSV")
    parser.add_argument("--user-summary", type=Path, help="可选：另存 UID/昵称/命中数统计 CSV")
    args = parser.parse_args(argv)

    keywords = normalize_keywords(args.keyword if args.keyword is not None else DEFAULT_KEYWORDS)
    if not keywords:
        parser.error("关键词不能为空")
    try:
        if args.fetch:
            rows = fetch_comments(Settings.load())
        elif args.source:
            rows = read_reviewed(args.source)
        else:
            parser.error("请提供 --source 评论 CSV 或 --fetch 在线抓取")

        matched = filter_comments(rows, keywords)
        names = _build_names_from_matches(matched)
        template = args.template.read_text(encoding="utf-8")
        page = render_page(template, names, statistics_at=latest_comment_time(matched))

        optional_outputs = [path.resolve() for path in (args.comments_output, args.user_summary) if path]
        targets = [args.output.resolve(), *optional_outputs]
        if len(targets) != len(set(targets)):
            raise ValueError("网页、评论明细和用户统计必须使用不同的输出路径")
        if args.comments_output:
            write_comments(args.comments_output, matched)
        if args.user_summary:
            write_user_summary(args.user_summary, matched)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(page, encoding="utf-8")
        temporary.replace(args.output)
        print(
            f"已生成 {args.output}：名单 {len(names)} 人，"
            f"命中评论 {len(matched)} 条，关键词：{'、'.join(keywords)}"
        )
        return 0
    except (BilibiliError, OSError, ValueError) as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
