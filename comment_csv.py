"""CSV export/import workflow for reviewed Bilibili comments."""

from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

FIELDS = [
    "渠道", "内容ID", "评论类型", "内容链接", "评论ID", "根评论ID", "父评论ID",
    "评论者UID", "评论者昵称", "评论内容", "发表时间", "点赞数", "是否回复", "回复内容",
]
RESULT_FIELDS = FIELDS + ["处理结果", "处理说明"]


def write_comments(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def read_reviewed(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_results(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def approved(value: str) -> bool:
    return str(value or "").strip().lower() in {"是", "回复", "同意", "yes", "y", "1", "true"}


def _csv_event(row: dict[str, str]) -> dict[str, Any]:
    """Convert one reviewed row to the normalized event used by memory/ledger."""
    comment_id = str(row.get("评论ID") or "").strip()
    root_id = row.get("根评论ID") or comment_id
    parent_id = row.get("父评论ID") or ""
    if str(root_id).isdigit():
        root_id = int(root_id)
    if str(parent_id).isdigit():
        parent_id = int(parent_id)
    return {
        "id": comment_id,
        "rpid": int(comment_id) if comment_id.isdigit() else comment_id,
        "oid": int(row["内容ID"]) if str(row.get("内容ID", "")).isdigit() else row.get("内容ID", ""),
        "root_id": root_id,
        "parent_id": parent_id,
        "type": int(row.get("评论类型") or 1),
        "content_type": row.get("评论类型") or "1",
        "uid": str(row.get("评论者UID") or ""),
        "username": str(row.get("评论者昵称") or "B站用户"),
        "text": str(row.get("评论内容") or ""),
        "like_count": row.get("点赞数") or 0,
        "time": _timestamp_from_csv(row.get("发表时间")),
    }


def _timestamp_from_csv(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError, OverflowError):
            return time.time()


def _audit_context(settings: Any) -> dict[str, Any] | None:
    state_dir = getattr(settings, "state_dir", None)
    if not state_dir:
        return None
    from event_store import EventStore
    from memory import MemoryStore
    from storage import JsonStore
    store = JsonStore(Path(state_dir))
    return {
        "state_dir": Path(state_dir),
        "store": store,
        "state": store.load("state.json", {}),
        "memory": MemoryStore(settings),
        "events": EventStore(Path(state_dir) / "events.sqlite3"),
    }


def _persist_successful_comment(settings: Any, event: dict[str, Any], reply: str, context: dict[str, Any] | None = None) -> bool:
    """Persist one real comment reply in both memory and the durable event ledger."""
    context = context or _audit_context(settings)
    if context is None:
        return False
    from llm import ReplyDecision
    state_dir = context["state_dir"]
    store = context["store"]
    state = context["state"]
    memory = context["memory"]
    channel = "评论"
    event_id = str(event.get("id") or event.get("rpid") or "")
    memory_key = f"{channel}:{event_id}" if event_id else ""
    if memory_key and memory_key in {str(item) for item in state.get("memory_event_keys", [])}:
        return False
    thread_id = f"comment:{event.get('oid', '')}:{event.get('root_id') or event.get('id', '')}"
    decision = ReplyDecision(reply=reply)
    recorded = memory.record(state, event, decision, channel, thread_id)
    memory.compact(state, str(event.get("uid", "")))
    events = context["events"]
    events.record_fetched(event, "comment")
    events.record_outcome(event, "comment", "replied", reply=reply, sent=True, attempt=True)
    if recorded:
        record = {
            "incoming_id": str(event.get("id", "")), "uid": str(event.get("uid", "")),
            "username": event.get("username", ""), "text": str(event.get("text", ""))[:500],
            "reply": reply, "sent": True, "simulated": False, "reason": "",
            "oid": event.get("oid", ""), "root_id": event.get("root_id", ""),
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        reply_log = state.setdefault("reply_log", {}).setdefault("comments", [])
        if not any(str(item.get("incoming_id", "")) == str(event.get("id", "")) for item in reply_log):
            reply_log.append(record)
            state["reply_log"]["comments"] = reply_log[-2000:]
    store.save("state.json", state)
    return bool(recorded)


def hydrate_sent_results(settings: Any, path: Path) -> dict[str, int]:
    """Backfill memory and event outcomes from a completed real-send CSV."""
    rows = read_reviewed(path)
    hydrated = 0
    already = 0
    skipped = 0
    context = _audit_context(settings)
    if context is None:
        raise ValueError("配置缺少 state_dir，无法写入记忆")
    # Hydration is an offline bookkeeping operation. Do not make one network
    # embedding request per historical row; lexical retrieval remains valid.
    if hasattr(context["memory"].settings, "embedding_api_key"):
        context["memory"].settings.embedding_api_key = ""
    for row in rows:
        if str(row.get("处理结果") or "").strip() != "已发送":
            skipped += 1
            continue
        event = _csv_event(row)
        if not event["id"] or not event["uid"]:
            skipped += 1
            continue
        if _persist_successful_comment(settings, event, str(row.get("回复内容") or ""), context):
            hydrated += 1
        else:
            already += 1
    cold_start = context["state"].setdefault("cold_start", {})
    cold_start["memory_hydrated_count"] = hydrated + already
    cold_start["memory_hydrated_at"] = datetime.now().isoformat(timespec="seconds")
    context["store"].save("state.json", context["state"])
    return {"hydrated": hydrated, "already": already, "skipped": skipped}


def reply_from_csv(client: Any, path: Path, result_path: Path) -> dict[str, int]:
    rows = read_reviewed(path)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = {"sent": 0, "simulated": 0, "skipped": 0, "failed": 0}
    batch_size = int(os.environ.get("REPLY_CSV_BATCH_SIZE", "0") or 0)
    batch_interval = float(os.environ.get("REPLY_CSV_BATCH_INTERVAL", "10") or 10)
    sent_in_batch = 0
    audit_context = _audit_context(getattr(client, "settings", None))
    for row in rows:
        item = dict(row)
        comment_id = str(row.get("评论ID") or "").strip()
        text = str(row.get("回复内容") or "").strip()
        reason = ""
        status = "跳过"
        if not approved(row.get("是否回复", "")):
            reason = "审核列未明确同意"
        elif not comment_id or not row.get("内容ID"):
            reason = "缺少内容ID或评论ID"
        elif not text:
            reason = "回复内容为空"
        elif comment_id in seen:
            reason = "评论ID重复"
        elif row.get("渠道") not in {"视频", "动态"}:
            reason = "不支持的渠道"
        else:
            try:
                comment_type = int(row.get("评论类型") or (1 if row.get("渠道") == "视频" else 17))
                allowed_types = {1} if row.get("渠道") == "视频" else {1, 11, 17}
                if comment_type not in allowed_types:
                    raise ValueError("评论类型与渠道不匹配")
                event = _csv_event(row)
                seen.add(comment_id)
                if audit_context:
                    previous = audit_context["events"].get(event, "comment")
                    if previous and previous.get("status") == "replied" and previous.get("sent"):
                        reason = "事件账本已记录真实回复，防止重复发送"
                        counts["skipped"] += 1
                        item.update({"处理结果": "跳过", "处理说明": reason})
                        results.append(item)
                        continue
                client.reply_comment(event, text)
                simulated = bool(client.settings.dry_run or getattr(client, "last_write_simulated", False))
                status = "模拟发送" if simulated else "已发送"
                counts["simulated" if simulated else "sent"] += 1
                if not simulated:
                    try:
                        _persist_successful_comment(client.settings, event, text, audit_context)
                    except Exception as exc:
                        # B站已确认发送；do not label it as a failed send and
                        # invite a manual retry just because local bookkeeping failed.
                        reason = f"已发送；本地账本写入失败：{type(exc).__name__}: {exc}"
                if not simulated:
                    sent_in_batch += 1
                    if batch_size and sent_in_batch >= batch_size:
                        sent_in_batch = 0
                        print(f"已发送 {counts['sent']} 条，休息 {batch_interval:g} 秒 ...", flush=True)
                        time.sleep(batch_interval)
            except Exception as exc:  # preserve per-row result and continue
                status = "失败"
                reason = f"{type(exc).__name__}: {exc}"
                counts["failed"] += 1
        if status == "跳过":
            counts["skipped"] += 1
        item.update({"处理结果": status, "处理说明": reason})
        results.append(item)
    write_results(result_path, results)
    print(
        f"发送完成：真实={counts['sent']} 模拟={counts['simulated']} "
        f"跳过={counts['skipped']} 失败={counts['failed']}",
        flush=True,
    )
    return counts
