"""Fetch public Bilibili stats for the homepage into home/bili.json.

Only public, login-free endpoints are used:
  - /x/space/arc/list        uploaded videos with play / like / reply / favorite counts
  - /x/relation/stat         follower count

When Bilibili rate-limits the request, the previous bili.json stays untouched
and the homepage keeps showing the last good copy.

Every successful run also appends one point to history.json
([unix秒, 粉丝, 总播放, 总点赞, 视频数]) so the page can draw growth curves.
The browser additionally polls /api/bili (Cloudflare Pages Function, see
functions/api/bili.js) for near-real-time numbers between CI runs.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HOME = Path(__file__).parent
OUT = HOME / "bili.json"
HISTORY = HOME / "history.json"
UID = os.environ.get("BILI_AGENT_BILI_USER_ID") or "3747573030456892"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": f"https://space.bilibili.com/{UID}",
}
BUVID = f"{str(uuid.uuid4()).upper()}infoc"
CST = timezone(timedelta(hours=8))
DAY_RE = re.compile(r"【\s*Day\s*(\d+)\s*】", re.I)


def normalize(archives: list[dict], follower: int, *, source: str) -> dict:
    videos = []
    for item in sorted(archives, key=lambda v: v["pubdate"]):
        stat = item.get("stat") or {}
        title = item.get("title", "")
        match = DAY_RE.search(title)
        pic = (item.get("pic") or "").replace("http://", "https://")
        videos.append(
            {
                "bvid": item["bvid"],
                "title": title,
                "day": int(match.group(1)) if match else None,
                "kind": "day" if match else ("extra" if "加更" in title else "other"),
                "pubdate": item["pubdate"],
                "duration": item.get("duration", 0),
                "pic": pic,
                "view": stat.get("view", 0),
                "like": stat.get("like", 0),
                "reply": stat.get("reply", 0),
                "favorite": stat.get("favorite", 0),
                "danmaku": stat.get("danmaku", 0),
                "share": stat.get("share", 0),
            }
        )
    return {
        "uid": UID,
        "space": f"https://space.bilibili.com/{UID}",
        "follower": follower,
        "videos": videos,
        "source": source,
        "updatedAt": datetime.now(CST).isoformat(timespec="seconds"),
    }


def get(url: str, params: dict) -> dict:
    cookies = {"buvid3": BUVID}
    if os.environ.get("BILI_AGENT_BILI_SESSDATA"):
        cookies["SESSDATA"] = os.environ["BILI_AGENT_BILI_SESSDATA"]
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=HEADERS, cookies=cookies, timeout=20)
        try:
            body = resp.json()
        except ValueError:
            body = {"code": -1, "message": f"HTTP {resp.status_code} 非 JSON"}
        if body.get("code") == 0:
            return body["data"]
        time.sleep(2 + attempt * 3)
    raise RuntimeError(f"{url} -> {body.get('code')} {body.get('message')}")


def fetch() -> dict:
    archives, page = [], 1
    while True:
        data = get(
            "https://api.bilibili.com/x/space/arc/list",
            {"mid": UID, "pn": page, "ps": 50},
        )
        archives += data.get("archives") or []
        total = (data.get("page") or {}).get("count", 0)
        if len(archives) >= total or not data.get("archives") or page >= 10:
            break
        page += 1
    follower = get("https://api.bilibili.com/x/relation/stat", {"vmid": UID}).get("follower", 0)
    return normalize(archives, follower, source="fetch")


def append_history(data: dict, path: Path = HISTORY) -> list:
    """One point per run; keep every point for 7 days, then one per day (last of the day)."""
    try:
        points = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except ValueError:
        points = []
    videos = data["videos"]
    now = int(time.time())
    points.append([now, data["follower"], sum(v["view"] for v in videos), sum(v["like"] for v in videos), len(videos)])
    points.sort(key=lambda p: p[0])
    recent = [p for p in points if p[0] >= now - 7 * 86400]
    daily: dict[str, list] = {}
    for p in points:
        if p[0] < now - 7 * 86400:
            daily[datetime.fromtimestamp(p[0], CST).strftime("%Y-%m-%d")] = p
    kept = (list(daily.values()) + recent)[-1500:]
    path.write_text(json.dumps(kept, separators=(",", ":")), encoding="utf-8")
    return kept


def main() -> int:
    try:
        data = fetch()
    except Exception as exc:  # 抓不到就保留上一版快照，主页照常构建
        print(f"[home] B 站数据抓取失败，沿用上一版 bili.json：{exc}", file=sys.stderr)
        return 0
    if not data["videos"]:
        print("[home] 接口返回 0 个视频，沿用上一版 bili.json", file=sys.stderr)
        return 0
    data["source"] = "ci"
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    append_history(data)
    print(f"[home] 视频 {len(data['videos'])} 个，粉丝 {data['follower']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
