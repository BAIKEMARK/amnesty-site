"""小游戏题库的自动维护：随站点每轮刷新一起跑。

做两件事：
  1. 真人题同步：从 data.json 里水位之后的新评论中，把「明显干净」的赦免申请加进 pool.json；
     可疑的（疑问句、叙事类、敏感词）放进 review/pending.json 等人工确认，其余直接忽略。
  2. 日题排期：保证北京时间「今天」起往后 AHEAD_DAYS 天的每日题都已排好并写进 pool.json。

任何一步出错都不该拦住站点刷新，调用方负责 try/except。
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

AHEAD_DAYS = 3  # 提前几天排好日题（今天 + 之后 3 天）
KEEP_DAILY_DAYS = 30
RECENT_DAYS = 14  # 日题里同一条 AI 题 / 真人题多久内不重复
MAX_ADMIT_PER_RUN = 40
MAX_REAL = 800
MAX_PENDING = 200
INITIAL_WATERMARK = "2026-10-28 00:00:00"

INTENT = re.compile(r"赦免|特赦|免死|丹书|铁券|饶我|放过我|名单")
TEMPLATE = re.compile(r"总而言之|尊敬的.{0,4}蓝色|^申请赦免，算我一个")
NARRATIVE = re.compile(r"会议|开会|报到|同类|散会|尾巴|主人|本鲸|我家人类|后排")
SENSITIVE = re.compile(r"孙笑川|安乐死|自杀|傻逼|操你|他妈|妈的|干死|约炮")
UNSAFE = re.compile(r"UID\s*[:：]?\s*\d{5,}|\d{8,}|https?://|[01]{16,}")
REPEAT = re.compile(r"(.{2,6})\1{2,}")
EMOTE = re.compile(r"\[[^\[\]]{1,30}\]")  # B 站表情码，如 [doge]、[大哭]、[xx 应援装扮_委屈]
REPLY = re.compile(r"^\s*(回复\s*)?@")  # 回复别人的串楼评论，不是自己的申请
NEGATE = re.compile(r"拒绝|不需要|不稀罕|不接受|才不")  # 明确不要赦免的，不是申请
OFFICIAL = re.compile(r"[⚡🐋🫧🌊]|掏小本本")  # 鲸鱼娘官方回复和同类二创回复的惯用标记

DM_CHANNEL = "私信"


def mask_uid(uid: str) -> str:
    """和前端 maskUid 保持一致。"""
    if "•" in uid:
        return uid
    if len(uid) > 5:
        return uid[:3] + "•" * max(2, len(uid) - 5) + uid[-2:]
    return uid[:1] + "••" + uid[-1:]


def beijing_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def read_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def write_json(path: Path, payload, indent: int | None = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    path.write_text(text + "\n", encoding="utf-8")


def text_key(person_id: str, text: str) -> str:
    return f"{person_id}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"


def clean(text: str) -> str:
    return EMOTE.sub("", text).strip()


def classify(text: str, channel: str) -> tuple[str, str]:
    """返回 (verdict, reason)：admit 直接收录；pending 待人工；skip 忽略。"""
    if channel == DM_CHANNEL or channel not in {"视频", "动态"}:
        return "skip", "非公开评论渠道"
    if not 6 <= len(text) <= 80 or "\n" in text:
        return "skip", "长度不合适"
    if REPLY.search(text) or OFFICIAL.search(text):
        return "skip", "回复他人或官方回复"
    if NEGATE.search(text):
        return "skip", "不是申请（拒绝赦免）"
    if UNSAFE.search(text) or REPEAT.search(text):
        return "skip", "含 UID、链接、乱码或刷屏"
    if TEMPLATE.search(text):
        return "skip", "模板句式，题库里已经够多"
    if not INTENT.search(text):
        return "skip", "不像赦免申请"
    if SENSITIVE.search(text):
        return "pending", "含敏感词"
    if NARRATIVE.search(text):
        return "pending", "叙事类，疑似 AI 或二创"
    if re.search(r"[？?]\s*$", text):
        return "pending", "疑问句，可能不是申请"
    return "admit", ""


def real_entry(person: dict, comment: dict, faces: dict) -> dict:
    face = faces.get(str(person["id"]), "")
    if not (isinstance(face, str) and face.startswith("https://") and "hdslb.com/" in face):
        face = ""
    return {
        "n": person["name"],
        "f": face,
        "u": mask_uid(str(person["id"])),
        "t": comment["text"],
        "d": comment["date"][:10],
        "c": comment["channel"],
        "k": str(person["id"]),
    }


def backfill_keys(real: list[dict], people: list[dict]) -> int:
    """老条目没有来源 UID：按昵称 + 原文在名册里对上号，之后退出名单才能精确剔除。"""
    index = {}
    for person in people:
        for comment in person["comments"]:
            index.setdefault((person["name"], comment["text"]), str(person["id"]))
    filled = 0
    for item in real:
        if not item.get("k"):
            uid = index.get((item["n"], item["t"]))
            if uid:
                item["k"] = uid
                filled += 1
    return filled


def sync_real(pool: dict, people: list[dict], faces: dict, excluded: set[str],
              review_dir: Path) -> dict:
    real = pool["real"]
    sync = pool.setdefault("sync", {})
    stats = {"admitted": 0, "pending": 0, "purged": 0, "applied": 0, "backfilled": 0}

    stats["backfilled"] = backfill_keys(real, people)
    before = len(real)
    real[:] = [item for item in real if item.get("k") not in excluded]
    stats["purged"] = before - len(real)

    pending_path = review_dir / "pending.json"
    rejected_path = review_dir / "rejected.json"
    pending = read_json(pending_path, [])
    rejected = set(read_json(rejected_path, []))

    # 先落实人工决定：approve 进题库，reject 进黑名单，没决定的原样保留。
    kept = []
    for item in pending:
        decision = item.get("decision", "")
        key = text_key(item["k"], item["t"])
        if decision == "approve" and item["k"] not in excluded:
            real.append({k: item[k] for k in ("n", "f", "u", "t", "d", "c", "k")})
            stats["applied"] += 1
        elif decision == "reject":
            rejected.add(key)
        elif decision == "":
            kept.append(item)
    pending = kept

    seen_text = {item["t"] for item in real}
    seen_pending = {text_key(item["k"], item["t"]) for item in pending}
    watermark = sync.get("watermark", INITIAL_WATERMARK)
    done_through = watermark  # 已处理到的评论时间；本轮放不下的留给下一轮
    fresh = []
    for person in people:
        if str(person["id"]) in excluded:
            continue
        for comment in person["comments"]:
            if comment["date"] > watermark:
                fresh.append((comment["date"], person, comment))
    fresh.sort(key=lambda row: row[0])

    for stamp, person, comment in fresh:
        text = clean(comment["text"])
        key = text_key(str(person["id"]), text)
        if key in rejected or text in seen_text or key in seen_pending:
            done_through = stamp
            continue
        verdict, reason = classify(text, comment["channel"])
        comment = {**comment, "text": text}
        if verdict == "admit":
            if stats["admitted"] >= MAX_ADMIT_PER_RUN or len(real) >= MAX_REAL:
                break
            real.append(real_entry(person, comment, faces))
            seen_text.add(text)
            stats["admitted"] += 1
        elif verdict == "pending" and len(pending) < MAX_PENDING:
            entry = real_entry(person, comment, faces)
            entry.update(reason=reason, decision="")
            pending.append(entry)
            seen_pending.add(key)
            stats["pending"] += 1
        done_through = stamp

    sync["watermark"] = done_through
    write_json(pending_path, pending)
    write_json(rejected_path, sorted(rejected))
    stats["pendingTotal"] = len(pending)
    stats["realTotal"] = len(real)
    return stats


def build_daily_set(pool: dict, day: str, recent_ai: set[str], recent_human: set[str]) -> tuple[list[dict], list[str]]:
    rng = random.Random(f"whale-daily-{day}")
    warnings = []

    humans = [r for r in pool["real"]
              if len(r["t"]) <= 60 and not TEMPLATE.search(r["t"]) and not NARRATIVE.search(r["t"])
              and not UNSAFE.search(r["t"])]
    ais = [t for t in pool["traps"] if t["kind"] == "ai" and t["level"] >= 2]

    fresh_humans = [r for r in humans if r["t"] not in recent_human]
    fresh_ais = [t for t in ais if t["id"] not in recent_ai]
    if len(fresh_humans) < 2:
        warnings.append(f"{day}: 近期没用过的真人题不足 2 条，已允许重复")
        fresh_humans = humans
    if len(fresh_ais) < 3:
        warnings.append(f"{day}: 近期没用过的 AI 题不足 3 条，已允许重复，请补充 AI 陷阱卡")
        fresh_ais = ais

    picked_h = rng.sample(fresh_humans, 2)
    picked_a = rng.sample(fresh_ais, 3)
    questions = [
        {"kind": "human", "text": r["t"], "name": r["n"], "face": r["f"], "date": r["d"], "channel": r["c"]}
        for r in picked_h
    ] + [{"kind": "ai", "id": t["id"], "text": t["text"], "tell": t["tell"]} for t in picked_a]
    rng.shuffle(questions)
    return questions, warnings


def schedule_daily(pool: dict, today: date) -> dict:
    daily = pool.setdefault("daily", {})
    warnings = []
    created = []
    for offset in range(AHEAD_DAYS + 1):
        day = (today + timedelta(days=offset)).isoformat()
        if day in daily:
            continue
        start = date.fromisoformat(day) - timedelta(days=RECENT_DAYS)
        recent = [q for d, qs in daily.items() if start <= date.fromisoformat(d) < date.fromisoformat(day) for q in qs]
        questions, notes = build_daily_set(
            pool, day,
            {q["id"] for q in recent if q["kind"] == "ai"},
            {q["text"] for q in recent if q["kind"] == "human"},
        )
        daily[day] = questions
        created.append(day)
        warnings += notes

    cutoff = (today - timedelta(days=KEEP_DAILY_DAYS)).isoformat()
    for day in [d for d in daily if d < cutoff]:
        del daily[day]
    pool["daily"] = dict(sorted(daily.items()))

    ai_pool = [t["id"] for t in pool["traps"] if t["kind"] == "ai" and t["level"] >= 2]
    used = {q["id"] for qs in daily.values() for q in qs if q["kind"] == "ai"}
    return {
        "created": created,
        "scheduledThrough": max(daily) if daily else "",
        "aiTrapsUnusedRecently": len([i for i in ai_pool if i not in used]),
        "warnings": warnings,
    }


def sync(data_path: Path, avatars_path: Path, exclude_path: Path, games_dir: Path,
         today: date | None = None) -> dict:
    today = today or beijing_today()
    pool_path = games_dir / "pool.json"
    pool = read_json(pool_path, None)
    if pool is None:
        raise FileNotFoundError(pool_path)

    data = read_json(data_path, {"people": []})
    faces = read_json(avatars_path, {})
    excluded = {str(uid) for uid in read_json(exclude_path, {}).get("uids", [])}

    real_stats = sync_real(pool, data["people"], faces, excluded, games_dir / "review")
    daily_stats = schedule_daily(pool, today)
    write_json(pool_path, pool)

    summary = {
        "updatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "real": real_stats,
        "daily": daily_stats,
    }
    write_json(games_dir / "sync-status.json", summary)
    return summary
