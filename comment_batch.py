"""Batch filtering and per-user summaries for exported Bilibili comments."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from comment_csv import read_reviewed, write_comments


USER_FIELDS = ["评论者UID", "评论者昵称", "命中评论数"]


def normalize_keywords(values: Iterable[str]) -> list[str]:
    """Trim empty phrases and preserve the order of distinct keywords."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = str(value or "").strip()
        folded = keyword.casefold()
        if keyword and folded not in seen:
            seen.add(folded)
            result.append(keyword)
    return result


def filter_comments(rows: Iterable[dict[str, Any]], keywords: Iterable[str]) -> list[dict[str, Any]]:
    """Select each comment once if it contains any case-insensitive phrase."""
    terms = [word.casefold() for word in normalize_keywords(keywords)]
    if not terms:
        raise ValueError("至少提供一个非空关键词")
    return [
        dict(row) for row in rows
        if any(term in str(row.get("评论内容") or "").casefold() for term in terms)
    ]


def user_summary(rows: Iterable[dict[str, Any]]) -> list[dict[str, str | int]]:
    """Count matched comments by commenter UID, retaining the displayed name."""
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for row in rows:
        uid = str(row.get("评论者UID") or "").strip()
        if not uid:
            continue
        counts[uid] += 1
        name = str(row.get("评论者昵称") or "").strip()
        if name:
            names[uid] = name
    return [
        {"评论者UID": uid, "评论者昵称": names.get(uid, "B站用户"), "命中评论数": count}
        for uid, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def write_user_summary(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = user_summary(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=USER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)
    return len(summary)


def filter_comment_file(
    source: Path,
    output: Path,
    keywords: Iterable[str],
    summary_path: Path | None = None,
) -> dict[str, int]:
    """Filter a saved comment CSV and write matches plus a commenter summary."""
    source_path = source.resolve()
    output_path = output.resolve()
    summary_resolved = summary_path.resolve() if summary_path is not None else None
    if source_path == output_path:
        raise ValueError("筛选结果不能覆盖输入 CSV")
    if summary_resolved is not None and summary_resolved in {source_path, output_path}:
        raise ValueError("用户统计 CSV 不能覆盖输入或筛选结果 CSV")
    terms = normalize_keywords(keywords)
    matches = filter_comments(read_reviewed(source), terms)
    write_comments(output, matches)
    if summary_path is not None:
        write_user_summary(summary_path, matches)
    return {"matched_comments": len(matches), "matched_users": len(user_summary(matches))}
