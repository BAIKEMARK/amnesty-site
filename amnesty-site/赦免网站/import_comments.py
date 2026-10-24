#!/usr/bin/env python3
"""Import UTF-8 CSV exports; preserve string UIDs, original wording and stable archive numbers.

Library use:
    from import_comments import load_data, merge_rows
CLI:
    python import_comments.py new-comments.csv
Default: merge with data.json. No automatic eligibility/approval decisions are made.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import csv
import json
import sys

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data.json"
REQUIRED = {"评论者UID", "评论者昵称", "评论内容", "发表时间", "内容链接", "渠道"}
SOURCE_NOTE = "B 站公开评论与私信；按 UID 合并，规则 + 模型判定"


def load_data(path: Path | str = DATA_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"people": []}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_rows(
    rows: Iterable[dict[str, Any]],
    data: dict[str, Any] | None = None,
    exclude: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, int]]:
    """Merge comment rows into the archive in memory.

    ``exclude`` is authoritative: listed UIDs are dropped from the existing
    archive and never re-added, so a manual removal survives the next refresh.
    """
    merged = dict(data or {"people": []})
    excluded = {str(item).strip() for item in exclude if str(item).strip()}
    people = {
        str(person["id"]): person
        for person in merged.get("people", [])
        if str(person.get("id")) not in excluded
    }
    removed = len(merged.get("people", [])) - len(people)
    highest = max((int(person.get("no") or 0) for person in people.values()), default=0)
    seen: dict[str, set[tuple[Any, Any, Any]]] = {
        uid: {(c.get("text"), c.get("date"), c.get("url")) for c in person.get("comments", [])}
        for uid, person in people.items()
    }

    added_people = added_comments = skipped_excluded = 0
    for row in rows:
        uid = str(row.get("评论者UID") or "").strip()
        if not uid.isdigit():
            raise ValueError("UID 不是数字字符串：" + repr(uid))
        if uid in excluded:
            skipped_excluded += 1
            continue
        if uid not in people:
            highest += 1
            people[uid] = {
                "id": uid,
                "name": str(row.get("评论者昵称") or "").strip() or "未署名人类",
                "no": highest,
                "comments": [],
            }
            seen[uid] = set()
            added_people += 1
        comment = {
            "text": str(row.get("评论内容") or "").strip(),
            "date": row.get("发表时间") or "",
            "url": row.get("内容链接") or "",
            "channel": row.get("渠道") or "",
        }
        via = str(row.get("matched_by") or "").strip()
        if via:
            comment["via"] = via
        why = str(row.get("why") or "").strip()
        if why:
            comment["why"] = why
        key = (comment["text"], comment["date"], comment["url"])
        if key not in seen[uid]:
            people[uid]["comments"].append(comment)
            seen[uid].add(key)
            added_comments += 1

    ordered = sorted(people.values(), key=lambda person: int(person.get("no") or 0))
    merged["source"] = SOURCE_NOTE
    merged["commentCount"] = sum(len(person.get("comments", [])) for person in ordered)
    merged["people"] = ordered
    stats = {
        "people": len(ordered),
        "comments": int(merged["commentCount"]),
        "addedPeople": added_people,
        "addedComments": added_comments,
        "removedByExclude": removed,
        "skippedExcluded": skipped_excluded,
    }
    return merged, stats


def output_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Keep only the keys the site consumes, in a stable order."""
    return {
        "source": data.get("source") or SOURCE_NOTE,
        "version": data.get("version") or "",
        "commentCount": int(data.get("commentCount") or 0),
        "people": data.get("people") or [],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("用法：python import_comments.py 新评论.csv")
    source = Path(args[0])
    rows = list(csv.DictReader(source.open(encoding="utf-8-sig", newline="")))
    if not rows or not REQUIRED.issubset(rows[0]):
        raise SystemExit("CSV 为空或缺少必要字段")

    data, stats = merge_rows(rows, load_data(DATA_PATH))
    DATA_PATH.write_text(
        json.dumps(output_payload(data), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"新增账号 {stats['addedPeople']}，新增留言 {stats['addedComments']}，"
        f"现有账号 {stats['people']}。请运行 python build.py 重新打包。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
