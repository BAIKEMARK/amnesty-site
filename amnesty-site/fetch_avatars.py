"""Build-time avatar sync: resolve each UID to its Bilibili face URL into avatars.json.

This never downloads images. The page references the Bilibili CDN URL directly
(``<img src="https://i0.hdslb.com/bfs/face/...">``), so the only cost is one API
lookup per UID -- and bulk lookups amortise that 50-fold.

Run locally or on a server; the browser page cannot call this API directly
(CORS / risk control).

Library use:
    from fetch_avatars import load_cache, sync_avatars
CLI:
    python fetch_avatars.py [--refresh]   Resumable; throttled.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json
import os
import random
import sys
import time
import urllib.request

ROOT = Path(__file__).parent
CACHE_PATH = ROOT / "avatars.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
THROTTLE_CODES = {-412, -352, -799}
# 批量接口（一次给一整串 UID 的卡片）必须登录态；超过 50 个会 code=0 但 data 为空，
# 所以 50 是实测上限，不能贪大。
BATCH_URL = "https://api.vc.bilibili.com/account/v1/user/cards?uids="
BATCH_SIZE = 50
BATCH_INTERVAL = 0.4


def load_cache(path: Path | str = CACHE_PATH) -> dict[str, str]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _headers(sessdata: str = "") -> dict[str, str]:
    headers = dict(HEADERS)
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


def _normalize_face(face: Any) -> str:
    value = str(face or "").replace("http://", "https://")
    return "" if "noface" in value else value


def _fetch_batch(uids: list[str], sessdata: str) -> dict[str, str]:
    """Return {uid: face_url}. Raises when the whole batch is unusable."""
    request = urllib.request.Request(BATCH_URL + ",".join(uids), headers=_headers(sessdata))
    payload = json.loads(urllib.request.urlopen(request, timeout=20).read())
    if payload.get("code") != 0:
        raise RuntimeError(f"code={payload.get('code')} {payload.get('message', '')}")
    got: dict[str, str] = {}
    for card in payload.get("data") or []:
        mid = str(card.get("mid") or "")
        if mid:
            got[mid] = _normalize_face(card.get("face", ""))
    if not got:
        raise RuntimeError("空响应")
    return got


def _fetch_batch_names(uids: list[str], sessdata: str) -> dict[str, str]:
    """Return public display names from the same authenticated card batch API."""
    request = urllib.request.Request(BATCH_URL + ",".join(uids), headers=_headers(sessdata))
    payload = json.loads(urllib.request.urlopen(request, timeout=20).read())
    if payload.get("code") != 0:
        raise RuntimeError(f"code={payload.get('code')} {payload.get('message', '')}")
    got = {
        str(card.get("mid")): str(card.get("name") or "").strip()
        for card in payload.get("data") or []
        if str(card.get("mid") or "") and str(card.get("name") or "").strip()
    }
    if not got:
        raise RuntimeError("批量用户卡片没有返回昵称")
    return got


def _fetch_one_name(uid: str, sessdata: str) -> str | None:
    """Single-card fallback, including accounts omitted by the batch endpoint."""
    request = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/card?mid={uid}", headers=_headers(sessdata)
    )
    payload = json.loads(urllib.request.urlopen(request, timeout=10).read())
    if payload.get("code") != 0:
        return None
    card = (payload.get("data") or {}).get("card") or {}
    return str(card.get("name") or "").strip() or None


def fetch_profile_names(
    uids: Iterable[str], sessdata: str = "", *, verbose: bool = True,
) -> tuple[dict[str, str], int]:
    """Resolve Bilibili display names for a UID list, with per-user fallbacks."""
    normalized = list(dict.fromkeys(
        str(uid).strip() for uid in uids if str(uid or "").strip().isdigit()
    ))
    names: dict[str, str] = {}
    failures = 0
    for start in range(0, len(normalized), BATCH_SIZE):
        chunk = normalized[start:start + BATCH_SIZE]
        if sessdata:
            try:
                names.update(_fetch_batch_names(chunk, sessdata))
            except Exception as exc:  # noqa: BLE001 - name enrichment must not stop roster refresh
                if verbose:
                    print(f"昵称批量查询 {start + 1}-{start + len(chunk)} 失败：{type(exc).__name__}: {exc}")
        missing = [uid for uid in chunk if uid not in names]
        for index, uid in enumerate(missing):
            try:
                name = _fetch_one_name(uid, sessdata)
            except Exception as exc:  # noqa: BLE001 - preserve placeholders on transient API errors
                name = None
                if verbose:
                    print(f"昵称查询失败 {uid}：{type(exc).__name__}: {exc}")
            if name:
                names[uid] = name
            else:
                failures += 1
            if index + 1 < len(missing):
                time.sleep(0.4)
        if start + BATCH_SIZE < len(normalized):
            time.sleep(BATCH_INTERVAL)
    return names, failures


def _fetch_one(uid: str, sessdata: str) -> tuple[str | None, int | None]:
    """Single-card fallback for UIDs the batch endpoint skips (closed/silent accounts)."""
    request = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/card?mid={uid}", headers=_headers(sessdata)
    )
    payload = json.loads(urllib.request.urlopen(request, timeout=10).read())
    code = payload.get("code")
    if code == 0:
        return _normalize_face(payload["data"]["card"].get("face", "")), 0
    if code in (-404, -626):
        return "", code
    return None, code


def sync_avatars(
    people: Iterable[dict[str, Any]],
    refresh: bool = False,
    cache_path: Path | str = CACHE_PATH,
    limit: int = 0,
    verbose: bool = True,
    sessdata: str = "",
) -> tuple[dict[str, str], int]:
    """Fill the cache for UIDs that have no entry yet. Returns (cache, failures)."""
    cache_path = Path(cache_path)
    cache = load_cache(cache_path)
    uid_list = [str(person["id"]) for person in people if str(person.get("id") or "").isdigit()]
    todo = [uid for uid in uid_list if refresh or uid not in cache]
    if limit:
        todo = todo[:limit]

    # ① 批量取外链：50 个 UID 一次，1.2 万人约 250 个请求。
    for start in range(0, len(todo), BATCH_SIZE):
        chunk = todo[start:start + BATCH_SIZE]
        try:
            got = _fetch_batch(chunk, sessdata)
        except Exception as exc:  # noqa: BLE001 - 整批失败就交给下面的逐个兜底
            if verbose:
                print(f"batch {start} 失败：{type(exc).__name__}: {exc}", flush=True)
            continue
        cache.update(got)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if verbose:
            print(f"{min(start + BATCH_SIZE, len(todo))} {len(todo)}", flush=True)
        time.sleep(BATCH_INTERVAL)

    # ② 批量没覆盖到的（注销、隐私、批量接口漏项）逐个补，匿名也能查。
    missing = [uid for uid in todo if uid not in cache]
    failures = 0
    for index, uid in enumerate(missing):
        try:
            face, code = _fetch_one(uid, sessdata)
        except Exception as exc:  # noqa: BLE001 - network variety, keep going
            failures += 1
            if verbose:
                print("err", uid, exc, flush=True)
            face, code = None, None
        if face is not None:
            cache[uid] = face
        else:
            failures += 1
            if verbose:
                print("code", code, uid, flush=True)
            if code in THROTTLE_CODES:
                time.sleep(30)
        if index % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.4 + random.random() * 0.4)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache, failures


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] or [])
    people = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))["people"]
    before = len(load_cache(CACHE_PATH))
    sessdata = os.environ.get("BILI_AGENT_BILI_SESSDATA", "")
    if not sessdata:
        config_path = ROOT.parent / "config.json"
        try:
            sessdata = str(json.loads(config_path.read_text(encoding="utf-8")).get("bili_sessdata") or "")
        except (OSError, ValueError):
            sessdata = ""
    cache, failures = sync_avatars(people, refresh="--refresh" in args, sessdata=sessdata)
    print("done", len(cache), "new", len(cache) - before, "fail", failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
