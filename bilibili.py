"""Bilibili HTTP gateway.

Only this module knows Bilibili endpoints. The agent can therefore be tested
with a fake gateway, and endpoint changes do not affect personality logic.
"""

from __future__ import annotations

import json
import hashlib
import re
import urllib.parse
import time
import uuid
import threading
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import requests

from config import Settings


class BilibiliError(RuntimeError):
    pass


class BilibiliApiError(BilibiliError):
    """The API returned an explicit non-success response."""


class BilibiliClient:
    API = "https://api.bilibili.com"
    SESSIONS_URL = "https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions"
    MESSAGES_URL = "https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs"
    SEND_MESSAGE_URL = "https://api.vc.bilibili.com/web_im/v1/web_im/send_msg"

    def __init__(
        self,
        settings: Settings,
        http: requests.Session | None = None,
        *,
        comment_request_interval: float = 0.2,
        comment_retry_attempts: int = 6,
    ):
        self.settings = settings
        self._owns_http = http is None
        self.http = http or requests.Session()
        self.comment_request_interval = max(0.0, float(comment_request_interval))
        self.comment_retry_attempts = max(1, int(comment_retry_attempts))
        self._comment_request_lock = threading.Lock()
        self._comment_last_request_at = 0.0
        # Lets the orchestration layer distinguish a preview from a real write
        # without changing the public boolean return value of these methods.
        self.last_write_simulated = False
        self.last_private_scan_errors = 0
        self.last_private_sessions_total = 0
        self.last_private_sessions_filtered = 0
        self.last_private_sessions_considered = 0
        self.last_private_sessions_requested = 0
        self.last_private_sessions_has_more = 0
        self.last_private_history_pages = 0
        if hasattr(self.http, "headers"):
            self.http.headers.update({
                "User-Agent": "Mozilla/5.0 BilibiliPersonalityAgent/1.0",
                "Referer": "https://www.bilibili.com/",
            })

    def _headers(self) -> dict[str, str]:
        return {
            "Cookie": (
                f"SESSDATA={self.settings.bili_sessdata}; "
                f"bili_jct={self.settings.bili_jct}; "
                f"DedeUserID={self.settings.bili_user_id}"
            ),
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }

    def _private_headers(self) -> dict[str, str]:
        """Headers used by the message service rather than comment APIs."""
        headers = self._headers()
        headers.update({
            "Referer": "https://message.bilibili.com/",
            "Origin": "https://message.bilibili.com",
        })
        return headers

    def _json(self, response: requests.Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise BilibiliApiError(f"code={payload.get('code')} {payload.get('message', '')}")
        return payload

    def _comment_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        """Make a throttled comment API request and retry transient failures."""
        for attempt in range(self.comment_retry_attempts):
            with self._comment_request_lock:
                wait = self.comment_request_interval - (time.monotonic() - self._comment_last_request_at)
                if wait > 0:
                    time.sleep(wait)
                self._comment_last_request_at = time.monotonic()
            try:
                return self._json(self.http.get(url, headers=self._headers(), params=params, timeout=15))
            except BilibiliApiError as exc:
                # -352 is Bilibili's rate-limit response. Other API errors are
                # usually permanent (invalid oid, unavailable content, etc.).
                retryable = "code=-352" in str(exc)
                if not retryable or attempt + 1 >= self.comment_retry_attempts:
                    raise
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if status is not None and status not in {408, 429} and status < 500:
                    raise
                if attempt + 1 >= self.comment_retry_attempts:
                    raise
            except requests.RequestException:
                if attempt + 1 >= self.comment_retry_attempts:
                    raise
            time.sleep(min(30.0, 1.0 * (2 ** attempt)))
        raise AssertionError("unreachable")

    def check_login(self) -> dict[str, Any]:
        payload = self._json(self.http.get(self.API + "/x/web-interface/nav", headers=self._headers(), timeout=15))
        data = payload.get("data") or {}
        return {"logged_in": bool(data.get("isLogin")), "uid": data.get("mid"), "username": data.get("uname", "")}

    def get_account_stats(self) -> dict[str, Any]:
        """Read the public account counters used by the daily dynamic writer."""
        nav = self._json(self.http.get(self.API + "/x/web-interface/nav", headers=self._headers(), timeout=15)).get("data") or {}
        mid = str(nav.get("mid") or self.settings.bili_user_id or "")
        result: dict[str, Any] = {"uid": mid, "username": str(nav.get("uname") or "")}
        relation = self._json(self.http.get(
            self.API + "/x/relation/stat", headers=self._headers(), params={"vmid": mid}, timeout=15,
        )).get("data") or {}
        upstat = self._json(self.http.get(
            self.API + "/x/space/upstat", headers=self._headers(), params={"mid": mid}, timeout=15,
        )).get("data") or {}
        result.update({
            "followers": int(relation.get("follower") or 0),
            "following": int(relation.get("following") or 0),
            "likes": int(upstat.get("likes") or 0),
            "archive_views": int((upstat.get("archive") or {}).get("view") or 0),
        })
        return result

    @staticmethod
    def _wbi_key(wbi_img: dict[str, Any]) -> str:
        image = "".join(
            str(wbi_img.get(name, "")).rsplit("/", 1)[-1].split(".")[0]
            for name in ("img_url", "sub_url")
        )
        table = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
                 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
                 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
                 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]
        if len(image) < max(table) + 1:
            return ""
        return "".join(image[index] for index in table)[:32]

    def _wbi_params(self, params: dict[str, Any], key: str) -> dict[str, Any]:
        signed = dict(params)
        signed["wts"] = int(time.time())
        query = "&".join(
            f"{name}={urllib.parse.quote(str(signed[name]), safe='!')}"
            for name in sorted(signed)
        )
        signed["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
        return signed

    def find_topic_id(self, topic_name: str) -> int | None:
        """Resolve a public Bilibili topic name to its numeric id.

        The dynamic write API stores the topic as metadata; putting ``#name#``
        in the text alone only creates a search link.  Topic search is public,
        so this lookup does not require a write operation.
        """
        name = str(topic_name or "").strip()
        if not name:
            return None
        try:
            payload = self._json(self.http.get(
                self.API + "/x/topic/pub/search",
                headers=self._headers(),
                params={"keywords": name, "page_num": 1, "page_size": 20},
                timeout=15,
            ))
        except Exception:
            return None
        items = ((payload.get("data") or {}).get("topic_items") or [])
        folded = name.casefold()
        for item in items:
            if str(item.get("name") or "").strip().casefold() == folded:
                try:
                    return int(item.get("id"))
                except (TypeError, ValueError):
                    return None
        # Bilibili may normalize the casing or return a localized display name.
        for item in items:
            candidate = str(item.get("name") or "").strip()
            if candidate and (folded in candidate.casefold() or candidate.casefold() in folded):
                try:
                    return int(item.get("id"))
                except (TypeError, ValueError):
                    return None
        return None

    def _comment_pages(self, oid: int | str, comment_type: int, limit: int = 0) -> list[dict[str, Any]]:
        """Fetch root comments and every page of replies in each thread."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset: str | None = None
        next_page = 0
        seen_offsets: set[str] = set()

        def add(item: dict[str, Any]) -> None:
            rid = str(item.get("rpid") or "")
            if rid and rid not in seen:
                seen.add(rid)
                result.append(item)

        def add_nested(items: list[dict[str, Any]]) -> None:
            for item in items:
                add(item)
                add_nested(item.get("replies") or [])

        def fetch_thread(root: dict[str, Any]) -> None:
            root_id = str(root.get("rpid") or "")
            if not root_id or ("rcount" in root and int(root.get("rcount") or 0) <= len(root.get("replies") or [])):
                return
            page_number = 1
            while True:
                data = self._comment_json(
                    self.API + "/x/v2/reply/reply",
                    params={"oid": oid, "type": comment_type, "root": root_id, "pn": page_number, "ps": 20},
                ).get("data") or {}
                batch = data.get("replies") or []
                for reply in batch:
                    add(reply)
                    add_nested(reply.get("replies") or [])
                total = int((data.get("page") or {}).get("count") or len(batch))
                if not batch:
                    if (page_number - 1) * 20 < total:
                        raise BilibiliError(f"楼中楼 {root_id} 提前结束，抓取未完成")
                    return
                if page_number * 20 >= total:
                    return
                page_number += 1

        while True:
            params: dict[str, Any] = {"oid": oid, "type": comment_type, "mode": 3, "next": next_page, "ps": 20}
            params["pagination_str"] = json.dumps({"offset": offset or ""}, separators=(",", ":"))
            data = self._comment_json(self.API + "/x/v2/reply/main", params=params).get("data") or {}
            batch = data.get("replies") or []

            for root in batch:
                add(root)
                add_nested(root.get("replies") or [])
                fetch_thread(root)
            cursor = data.get("cursor") or {}
            if limit and len(result) >= limit:
                return result[:limit]
            if cursor.get("is_end"):
                return result
            if not batch:
                raise BilibiliError(f"评论列表提前结束，内容 {oid} 的抓取未完成")
            offset = (cursor.get("pagination_reply") or {}).get("next_offset")
            if not offset:
                raise BilibiliError(f"评论分页游标缺失，内容 {oid} 的抓取未完成")
            offset = str(offset)
            if offset in seen_offsets:
                raise BilibiliError(f"评论分页游标重复，内容 {oid} 的抓取未完成")
            seen_offsets.add(offset)
            next_page = int(cursor.get("next") or (next_page + 1))

    def get_owned_videos(self, limit: int = 0) -> list[dict[str, Any]]:
        nav = self._json(self.http.get(self.API + "/x/web-interface/nav", headers=self._headers(), timeout=15)).get("data") or {}
        key = self._wbi_key(nav.get("wbi_img") or {})
        page = 1
        videos: list[dict[str, Any]] = []
        seen_video_ids: set[str] = set()
        while True:
            payload = self._json(self.http.get(
                self.API + "/x/space/wbi/arc/search", headers=self._headers(),
                params=self._wbi_params({"mid": nav.get("mid"), "pn": page, "ps": 30, "order": "pubdate"}, key), timeout=15,
            ))
            data = payload.get("data") or {}
            batch = ((data.get("list") or {}).get("vlist") or [])
            batch_ids = [str(video.get("aid") or video.get("bvid") or "") for video in batch]
            if any(video_id and video_id in seen_video_ids for video_id in batch_ids):
                raise BilibiliError(f"账号投稿列表第 {page} 页出现重复项目，抓取未完成")
            seen_video_ids.update(video_id for video_id in batch_ids if video_id)
            videos.extend(batch)
            reported_total = (data.get("page") or {}).get("count") or None
            if not batch:
                if reported_total is not None and len(videos) < int(reported_total):
                    raise BilibiliError(f"账号投稿列表提前结束：已读取 {len(videos)}/{reported_total} 个视频")
                return videos[:limit] if limit else videos
            if (reported_total is not None and len(videos) >= int(reported_total)) or (limit and len(videos) >= limit):
                return videos[:limit] if limit else videos
            page += 1

    def get_owned_video_stats(self, limit: int = 10) -> list[dict[str, Any]]:
        """Attach current public counters to the account's most recent videos."""
        videos = self.get_owned_videos(limit=limit)
        def fetch(video: dict[str, Any]) -> dict[str, Any]:
            row = dict(video)
            bvid = str(video.get("bvid") or "")
            if bvid:
                try:
                    data = self._json(self.http.get(
                        self.API + "/x/web-interface/view", headers=self._headers(),
                        params={"bvid": bvid}, timeout=15,
                    )).get("data") or {}
                    stat = data.get("stat") or {}
                    row.update({"title": data.get("title") or row.get("title") or "", "stat": {
                        key: int(stat.get(key) or 0)
                        for key in ("view", "like", "reply", "favorite", "coin", "share", "danmaku")
                    }})
                except Exception as exc:
                    row["stats_error"] = type(exc).__name__
            return row
        if len(videos) < 2:
            return [fetch(video) for video in videos]
        with ThreadPoolExecutor(max_workers=min(5, len(videos))) as pool:
            return list(pool.map(fetch, videos))

    def get_video_comments(self, bvid: str, limit: int = 0) -> tuple[int, list[dict[str, Any]]]:
        """Fetch visible comments and nested replies for one BV only."""
        bvid = str(bvid or "").strip()
        if not re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid):
            raise BilibiliError("无效的 BV 号")
        payload = self._json(self.http.get(
            self.API + "/x/web-interface/view", headers=self._headers(),
            params={"bvid": bvid}, timeout=15,
        ))
        data = payload.get("data") or {}
        aid = data.get("aid")
        if not aid:
            raise BilibiliError(f"无法解析视频 {bvid} 的 aid")
        return int(aid), self._comment_pages(int(aid), 1, limit)

    def get_owned_dynamics(self, limit: int = 0) -> list[dict[str, Any]]:
        url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
        offset = ""
        seen_offsets: set[str] = set()
        items: list[dict[str, Any]] = []
        while True:
            data = self._json(self.http.get(url, headers=self._headers(), params={
                "host_mid": self.settings.bili_user_id, "offset": offset,
                "timezone_offset": -480, "features": "itemOpusStyle",
            }, timeout=15)).get("data") or {}
            batch = data.get("items") or []
            items.extend(batch)
            if limit and len(items) >= limit:
                return items[:limit] if limit else items
            if not data.get("has_more"):
                return items
            next_offset = str(data.get("offset") or "")
            if not next_offset:
                raise BilibiliError("账号动态列表仍有下一页，但未返回分页游标")
            if next_offset == offset or next_offset in seen_offsets:
                raise BilibiliError("账号动态列表分页游标重复，抓取未完成")
            seen_offsets.add(next_offset)
            offset = next_offset

    @staticmethod
    def comment_record(comment: dict[str, Any], *, channel: str, oid: int | str, comment_type: int, url: str = "") -> dict[str, Any]:
        member = comment.get("member") or {}
        content = comment.get("content") or {}
        timestamp = comment.get("ctime") if comment.get("ctime") is not None else ""
        if str(timestamp).isdigit():
            try:
                china_time = timezone(timedelta(hours=8))
                timestamp = datetime.fromtimestamp(int(timestamp), china_time).strftime("%Y-%m-%d %H:%M:%S")
            except (OverflowError, OSError, ValueError):
                timestamp = str(timestamp)
        return {
            "渠道": channel, "内容ID": str(oid), "评论类型": str(comment_type), "内容链接": url,
            "评论ID": str(comment.get("rpid") or ""), "根评论ID": str(comment.get("root") or comment.get("rpid") or ""),
            "父评论ID": str(comment.get("parent") or ""), "评论者UID": str(member.get("mid") or comment.get("mid") or ""),
            "评论者昵称": str(member.get("uname") or "B站用户"), "评论内容": str(content.get("message") or ""),
            "发表时间": str(timestamp), "点赞数": str(comment.get("like") or 0),
            "是否回复": "", "回复内容": "",
        }

    def export_owned_comments(
        self,
        limit_per_content: int = 0,
        progress: Callable[[str, int, int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch visible comments on every owned video and dynamic.

        If any content cannot be fully read, raise instead of returning a
        partial result. The caller should only write the CSV after success.
        ``progress`` receives channel, completed count, total count, and the
        number of rows collected so far.
        """
        records: list[dict[str, Any]] = []
        try:
            videos = self.get_owned_videos()
        except Exception as exc:
            if isinstance(exc, BilibiliError):
                raise
            raise BilibiliError(f"账号投稿列表抓取失败：{type(exc).__name__}: {exc}") from exc
        for index, video in enumerate(videos, start=1):
            aid, bvid = video.get("aid"), video.get("bvid")
            if not aid:
                raise BilibiliError(f"投稿列表第 {index} 项缺少 aid，无法确认评论抓取完整")
            url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
            try:
                found = self._comment_pages(aid, 1, limit_per_content)
            except Exception as exc:
                raise BilibiliError(f"视频 {bvid or aid} 评论抓取未完成：{type(exc).__name__}: {exc}") from exc
            records.extend(self.comment_record(x, channel="视频", oid=aid, comment_type=1, url=url) for x in found)
            if progress:
                progress("视频", index, len(videos), len(records))
        try:
            dynamics = self.get_owned_dynamics()
        except Exception as exc:
            if isinstance(exc, BilibiliError):
                raise
            raise BilibiliError(f"账号动态列表抓取失败：{type(exc).__name__}: {exc}") from exc
        for index, item in enumerate(dynamics, start=1):
            basic = item.get("basic") or {}
            oid = basic.get("comment_id_str") or item.get("id_str")
            comment_type = int(basic.get("comment_type") or 17)
            if not oid:
                continue
            url = f"https://www.bilibili.com/opus/{item.get('id_str')}" if item.get("id_str") else ""
            try:
                found = self._comment_pages(oid, comment_type, limit_per_content)
            except Exception as exc:
                raise BilibiliError(f"动态 {item.get('id_str') or oid} 评论抓取未完成：{type(exc).__name__}: {exc}") from exc
            records.extend(self.comment_record(x, channel="动态", oid=oid, comment_type=comment_type, url=url) for x in found)
            if progress:
                progress("动态", index, len(dynamics), len(records))
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for record in records:
            key = (record["评论类型"], record["内容ID"], record["评论ID"])
            if key not in unique or record["渠道"] == "视频":
                unique[key] = record
        return list(unique.values())

    def get_new_replies(self, limit: int = 10) -> list[dict[str, Any]]:
        result = []
        target = max(1, int(limit))
        # The endpoint accepts a larger page size.  Using one page avoids a
        # known proxy/server hang observed when requesting page 2 with ps=20.
        # If a deployment caps the response at 20, the pagination fallback
        # below still preserves the old behavior.
        page_size = min(target, 100)
        seen_ids: set[str] = set()
        page = 1
        while len(result) < target:
            payload = self._json(self.http.get(
                self.API + "/x/msgfeed/reply",
                headers=self._headers(),
                params={"ps": page_size, "pn": page},
                timeout=15,
            ))
            items = list((payload.get("data") or {}).get("items", []))
            for item in items:
                raw = item.get("item") or {}
                event_id = str(raw.get("source_id") or "")
                if not event_id or not raw.get("subject_id") or event_id in seen_ids:
                    continue
                user = item.get("user") or {}
                if str(user.get("mid") or "") == str(self.settings.bili_user_id or ""):
                    continue
                seen_ids.add(event_id)
                result.append({
                    "id": event_id,
                    "rpid": int(raw.get("source_id") or 0),
                    "oid": int(raw.get("subject_id") or 0),
                    "root_id": int(raw.get("root_id") or raw.get("source_id") or 0),
                    "type": int(raw.get("business_id") or 1),
                    "text": str(raw.get("source_content") or "").strip(),
                    "uid": str(user.get("mid") or ""),
                    "username": str(user.get("nickname") or "B站用户"),
                    "like_count": int(raw.get("like_count") or item.get("like_count") or 0),
                    "raw": item,
                })
                if len(result) >= target:
                    break
            if len(items) < page_size and not (target > 20 and len(items) == 20):
                break
            page += 1
        return result

    def reply_comment(self, event: dict[str, Any], text: str) -> bool:
        if self.settings.dry_run:
            self.last_write_simulated = True
            print(f"[DRY-RUN] 回复评论 {event.get('id')}: {text}")
            return True
        self.last_write_simulated = False
        data = {
            "oid": event["oid"],
            "type": event.get("type", 1),
            "root": event.get("root_id") or event["rpid"],
            "parent": event["rpid"],
            "message": text,
            "csrf": self.settings.bili_jct,
        }
        self._json(self.http.post(self.API + "/x/v2/reply/add", headers=self._headers(), data=data, timeout=15))
        return True

    @staticmethod
    def _content(raw: Any, msg_type: int) -> tuple[str, str]:
        if msg_type == 1:
            if isinstance(raw, dict):
                return str(raw.get("content") or raw.get("text") or "").strip(), "text"
            try:
                value = json.loads(str(raw or ""))
                return str(value.get("content") or value.get("text") or "").strip(), "text"
            except (TypeError, ValueError):
                return str(raw or "").strip(), "text"
        if msg_type == 7:
            try:
                value = raw if isinstance(raw, dict) else json.loads(str(raw or ""))
            except (TypeError, ValueError):
                return "", ""
            bvid = str(value.get("bvid") or "").strip()
            title = str(value.get("title") or value.get("headline") or "").strip()
            if bvid.startswith("BV"):
                return f"[B站视频分享] {title}\nhttps://www.bilibili.com/video/{bvid}".strip(), "video_share"
        return f"[未解析的私信消息类型 {msg_type}]", f"unsupported_{msg_type}"

    def _get_sessions(self) -> list[dict[str, Any]]:
        return self._get_sessions_page()

    def _get_sessions_page(self, *, end_ts: int | None = None, unfollow_fold: int = 0) -> list[dict[str, Any]]:
        params = {
            "session_type": 1, "group_fold": 1, "unfollow_fold": 0,
            "sort_rule": 2, "size": 100, "build": 0, "mobi_app": "web",
        }
        params["unfollow_fold"] = unfollow_fold
        if end_ts is not None:
            params["end_ts"] = int(end_ts)
        payload = self._json(self.http.get(self.SESSIONS_URL, headers=self._private_headers(), params=params, timeout=15))
        data = payload.get("data") or {}
        self.last_private_sessions_has_more = int(data.get("has_more") or 0)
        return list(data.get("session_list") or [])

    def _get_all_private_sessions(self) -> list[dict[str, Any]]:
        """Page through normal and folded sessions using the timestamp cursor."""
        sessions: dict[str, dict[str, Any]] = {}
        filtered: set[str] = set()
        unresolved = 0
        for fold in (0, 1):
            end_ts: int | None = None
            seen_ends: set[int] = set()
            for _ in range(100):
                page = self._get_sessions_page(end_ts=end_ts, unfollow_fold=fold)
                if not page:
                    break
                for item in page:
                    talker = int(item.get("talker_id") or 0)
                    if not talker:
                        continue
                    key = f"1:{talker}"
                    if int(item.get("session_type") or 1) == 1 and not int(item.get("system_msg_type") or 0) and not int(item.get("group_type") or 0):
                        sessions[key] = item
                    else:
                        filtered.add(key)
                if not self.last_private_sessions_has_more:
                    break
                oldest = min(int(item.get("session_ts") or 0) for item in page)
                if oldest <= 0 or oldest in seen_ends:
                    unresolved += 1
                    break
                seen_ends.add(oldest)
                end_ts = oldest
            else:
                unresolved += 1
        self.last_private_sessions_has_more = unresolved
        self.last_private_sessions_filtered = len(filtered)
        return list(sessions.values())

    def _fetch_session(self, talker_id: int, session_type: int, begin_seqno: int) -> dict[str, Any]:
        payload = self._json(self.http.get(self.MESSAGES_URL, headers=self._private_headers(), params={
            "talker_id": talker_id, "session_type": session_type,
            "begin_seqno": begin_seqno, "size": 20, "sender_device_id": 1,
            "build": 0, "mobi_app": "web",
        }, timeout=15))
        return payload.get("data") or {}

    def get_private_history(self, *, concurrency: int = 4) -> list[dict[str, Any]]:
        """Read all messages exposed by the current private-message sessions.

        This method is deliberately read-only: it does not load or update the
        polling state. Sessions are fetched concurrently, while pages within a
        session are read in sequence using ``min_seqno - 1`` when required.
        """
        sessions = self._get_all_private_sessions()
        self.last_private_sessions_total = len(sessions)
        self.last_private_history_pages = 0
        self.last_private_scan_errors = 0
        local = threading.local()

        def fetch(session: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], int, Exception | None]:
            talker = int(session.get("talker_id") or 0)
            reader = self
            if self._owns_http:
                reader = getattr(local, "client", None)
                if reader is None:
                    reader = BilibiliClient(self.settings)
                    local.client = reader
            begin = 0
            pages: list[dict[str, Any]] = []
            seen_ranges: set[tuple[int, int]] = set()
            try:
                for _ in range(100):
                    data = reader._fetch_session(talker, 1, begin)
                    pages.append(data)
                    if not data.get("has_more"):
                        break
                    minimum = int(data.get("min_seqno") or 0)
                    if minimum <= 0:
                        break
                    next_begin = minimum - 1
                    bounds = (begin, next_begin)
                    if next_begin == begin or bounds in seen_ranges:
                        break
                    seen_ranges.add(bounds)
                    begin = next_begin
                return session, pages, len(pages), None
            except Exception as exc:
                return session, pages, len(pages), exc

        workers = min(max(1, int(concurrency)), max(1, len(sessions)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(fetch, sessions))

        account_uid = str(self.settings.bili_user_id or "")
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for session, pages, page_count, error in fetched:
            self.last_private_history_pages += page_count
            if error is not None:
                self.last_private_scan_errors += 1
                continue
            talker = int(session.get("talker_id") or 0)
            key = f"1:{talker}"
            account = session.get("account_info") or {}
            username = str(account.get("name") or account.get("uname") or f"UID {talker}")
            for data in pages:
                for raw in data.get("messages") or []:
                    msg_key = str(raw.get("msg_key") or raw.get("msg_seqno") or "")
                    if not msg_key or msg_key in seen:
                        continue
                    msg_type = int(raw.get("msg_type") or 0)
                    text, content_type = self._content(raw.get("content"), msg_type)
                    if not text:
                        continue
                    try:
                        stamp = float(raw.get("timestamp") or 0)
                        if stamp > 1e12:
                            stamp /= 1000
                    except (TypeError, ValueError):
                        stamp = 0
                    sender = str(raw.get("sender_uid") or talker)
                    seen.add(msg_key)
                    events.append({
                        "id": msg_key, "uid": sender,
                        "username": "本账号" if sender == account_uid else username,
                        "text": text, "time": stamp, "content_type": content_type,
                        "session_type": 1, "direction": "outgoing" if sender == account_uid else "incoming",
                        "_session_key": key, "_seqno": int(raw.get("msg_seqno") or 0),
                        "_msg_key": msg_key,
                    })
        events.sort(key=lambda item: (item["_session_key"], item["_seqno"], item["time"]))
        return events

    def get_recent_private_messages(
        self,
        *,
        since_minutes: int = 10,
        state: dict[str, Any] | None = None,
        limit: int | None = None,
        concurrency: int = 4,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch incoming messages in a recent time window without moving cursors."""
        if since_minutes < 1:
            raise ValueError("since_minutes must be at least 1")
        now = time.time() if now is None else float(now)
        cutoff = now - since_minutes * 60
        state = state or {}
        cursors = state.get("private_sessions") or {}
        sessions = [
            session for session in self._get_sessions()
            if int(session.get("talker_id") or 0)
            and int(session.get("session_type") or 1) == 1
        ]
        self.last_private_sessions_total = len(sessions)
        # New sessions have no local cursor. Their list timestamp is enough to
        # avoid opening all 100 conversations; existing cursors are always
        # checked because a session may have received a message since the
        # previous scan.
        sessions = [
            session for session in sessions
            if f"1:{int(session.get('talker_id') or 0)}" in cursors
            or float(session.get("session_ts") or 0) / 1_000_000 >= cutoff
            or float((session.get("last_msg") or {}).get("timestamp") or 0) >= cutoff
        ]
        self.last_private_sessions_considered = len(sessions)
        sessions = [
            session for session in sessions
            if f"1:{int(session.get('talker_id') or 0)}" not in cursors
            or not int(session.get("max_seqno") or 0)
            or int(session.get("max_seqno") or 0) > int(cursors.get(f"1:{int(session.get('talker_id') or 0)}") or 0)
        ]
        self.last_private_sessions_requested = len(sessions)
        self.last_private_scan_errors = 0
        if not sessions:
            return []

        local = threading.local()

        def fetch(session: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Exception | None]:
            talker = int(session.get("talker_id") or 0)
            session_key = f"1:{talker}"
            remote_max = int(session.get("max_seqno") or 0)
            if session_key in cursors:
                begin_seqno = int(cursors.get(session_key) or 0)
                if remote_max and remote_max <= begin_seqno:
                    return session, {}, None
            else:
                # A new session has no local cursor; start near its remote tail.
                begin_seqno = max(0, remote_max - 20)

            reader = self
            if self._owns_http:
                reader = getattr(local, "client", None)
                if reader is None:
                    reader = BilibiliClient(self.settings)
                    local.client = reader
            try:
                return session, reader._fetch_session(talker, 1, begin_seqno), None
            except Exception as exc:  # one bad conversation must not drop the batch
                return session, {}, exc

        workers = min(max(1, int(concurrency)), len(sessions))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(fetch, sessions))

        messages: list[dict[str, Any]] = []
        seen: set[str] = set()
        self.last_private_scan_errors = sum(error is not None for _session, _data, error in fetched)
        account_uid = str(self.settings.bili_user_id or "")
        for session, data, error in fetched:
            if error is not None:
                talker = int(session.get("talker_id") or 0)
                print(f"[私信] 会话 {talker} 拉取失败，已跳过本次：{type(error).__name__}")
                continue
            if not data:
                continue
            talker = int(session.get("talker_id") or 0)
            account = session.get("account_info") or {}
            username = str(account.get("name") or account.get("uname") or "私信用户")
            for raw in sorted(data.get("messages") or [], key=lambda item: int(item.get("msg_seqno") or 0)):
                msg_key = str(raw.get("msg_key") or raw.get("msg_seqno") or "")
                if not msg_key or msg_key in seen or str(raw.get("sender_uid") or "") == account_uid:
                    continue
                msg_type = int(raw.get("msg_type") or 0)
                if msg_type not in (1, 7):
                    continue
                try:
                    stamp = float(raw.get("timestamp"))
                    if stamp > 1e12:
                        stamp /= 1000
                except (TypeError, ValueError):
                    continue
                if stamp < cutoff or stamp > now + 300:
                    continue
                session_key = f"1:{talker}"
                cursor = int(cursors.get(session_key) or 0)
                seqno = int(raw.get("msg_seqno") or 0)
                if cursor and seqno and seqno <= cursor:
                    continue
                text, content_type = self._content(raw.get("content"), msg_type)
                if not text:
                    continue
                seen.add(msg_key)
                messages.append({
                    "id": msg_key,
                    "uid": str(raw.get("sender_uid") or talker),
                    "username": username,
                    "text": text,
                    "time": stamp,
                    "content_type": content_type,
                    "session_type": 1,
                    "_session_key": f"1:{talker}",
                    "_seqno": seqno,
                    "_msg_key": msg_key,
                })
        messages.sort(key=lambda item: (item["time"], item["_seqno"]))
        max_messages = max(1, int(limit if limit is not None else self.settings.max_messages_per_poll))
        return messages[-max_messages:]

    def poll_private_messages(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        sessions = self._get_sessions()
        account_uid = str(self.settings.bili_user_id or "")
        if state.get("private_account_uid") != account_uid:
            state.update({"private_initialized": False, "private_account_uid": account_uid, "private_sessions": {}, "private_processed": [], "private_inflight": {}})
        session_state = state.setdefault("private_sessions", {})
        processed = set(str(x) for x in state.setdefault("private_processed", []))
        inflight = {str(k): int(v or 0) for k, v in state.setdefault("private_inflight", {}).items()}
        if not state.get("private_initialized"):
            for session in sessions:
                talker = int(session.get("talker_id") or 0)
                if talker:
                    session_state[f"1:{talker}"] = int(session.get("max_seqno") or 0)
            state["private_initialized"] = True
            print("[私信] 首次初始化完成，已跳过历史消息")
            return []

        messages: list[dict[str, Any]] = []
        max_per_poll = max(1, self.settings.max_messages_per_poll)
        self_uid = str(self.settings.bili_user_id)
        for session in sessions:
            if len(messages) >= max_per_poll:
                break
            talker = int(session.get("talker_id") or 0)
            if not talker or int(session.get("session_type") or 1) != 1:
                continue
            key = f"1:{talker}"
            last_seqno = int(session_state.get(key) or 0)
            remote_max = int(session.get("max_seqno") or 0)
            if remote_max and remote_max <= last_seqno:
                continue
            data = self._fetch_session(talker, 1, last_seqno)
            raw_messages = list(data.get("messages") or [])
            safe_cursor = last_seqno
            has_uncommitted = False
            for raw in sorted(raw_messages, key=lambda item: int(item.get("msg_seqno") or 0)):
                msg_key = str(raw.get("msg_key") or raw.get("msg_seqno") or "")
                seqno = int(raw.get("msg_seqno") or 0)
                sender = str(raw.get("sender_uid") or "")
                if msg_key in inflight:
                    has_uncommitted = True
                    continue
                if not msg_key or msg_key in processed or sender == self_uid or int(raw.get("msg_type") or 0) not in (1, 7):
                    if not has_uncommitted:
                        safe_cursor = max(safe_cursor, seqno)
                    continue
                content, kind = self._content(raw.get("content"), int(raw.get("msg_type") or 0))
                if not content:
                    if not has_uncommitted:
                        safe_cursor = max(safe_cursor, seqno)
                    continue
                has_uncommitted = True
                account = session.get("account_info") or {}
                messages.append({
                    "id": msg_key,
                    "uid": sender or str(talker),
                    # The numeric talker id is internal metadata, never a
                    # public display name that should reach the model/user.
                    "username": str(account.get("name") or account.get("uname") or "私信用户"),
                    "text": content,
                    "content_type": kind,
                    "session_type": 1,
                    "_session_key": key,
                    "_seqno": seqno,
                    "_msg_key": msg_key,
                })
                inflight[msg_key] = seqno
                processed.add(msg_key)
                if len(messages) >= max_per_poll:
                    break
            # Consume messages that cannot ever become an event (our own
            # messages, unsupported message types, malformed content).  A
            # cursor is never moved past a candidate event; those are committed
            # one by one by the orchestration layer.
            if safe_cursor > last_seqno and not has_uncommitted:
                session_state[key] = safe_cursor
        state["private_inflight"] = inflight
        return messages

    @staticmethod
    def commit_private_event(
        state: dict[str, Any], event: dict[str, Any], *, advance_cursor: bool = True,
    ) -> None:
        """Mark a private event done, optionally advancing the polling cursor."""
        key = str(event.get("_session_key") or "")
        msg_key = str(event.get("_msg_key") or event.get("id") or "")
        seqno = int(event.get("_seqno") or 0)
        if key and advance_cursor:
            sessions = state.setdefault("private_sessions", {})
            sessions[key] = max(int(sessions.get(key) or 0), seqno)
        inflight = state.setdefault("private_inflight", {})
        if msg_key:
            inflight.pop(msg_key, None)
        if msg_key:
            processed = [str(item) for item in state.setdefault("private_processed", [])]
            if msg_key not in processed:
                processed.append(msg_key)
            state["private_processed"] = processed[-1000:]

    def send_private_message(self, uid: str, text: str, session_type: int = 1) -> bool:
        if self.settings.dry_run:
            self.last_write_simulated = True
            print(f"[DRY-RUN] 私信 {uid}: {text}")
            return True
        self.last_write_simulated = False
        if not self.settings.bili_user_id or not self.settings.bili_jct:
            raise BilibiliError("发送私信需要 bili_user_id 和 bili_jct")
        form = {
            "msg[sender_uid]": str(self.settings.bili_user_id),
            "msg[receiver_id]": str(uid), "msg[receiver_type]": str(session_type),
            "msg[msg_type]": "1", "msg[msg_status]": "0",
            "msg[dev_id]": str(uuid.uuid4()).upper(),
            "msg[timestamp]": str(int(time.time() * 1000)),
            "msg[content]": json.dumps({"content": text}, ensure_ascii=False),
            "msg[new_face_version]": "0", "from_firework": "0", "build": "0",
            "mobi_app": "web", "csrf_token": self.settings.bili_jct, "csrf": self.settings.bili_jct,
        }
        self._json(self.http.post(self.SEND_MESSAGE_URL, headers=self._private_headers(), data=form, timeout=15))
        return True

    def _post_dynamic_with_topic(self, text: str, topic_id: int) -> bool:
        """Publish a text dynamic through the metadata-aware v2 endpoint."""
        nav = self._json(self.http.get(self.API + "/x/web-interface/nav", headers=self._headers(), timeout=15)).get("data") or {}
        key = self._wbi_key(nav.get("wbi_img") or {})
        if not key:
            raise BilibiliError("无法取得动态发布所需的 WBI 参数")
        params = self._wbi_params({
            "csrf": self.settings.bili_jct,
            "web_location": 1550101,
            "dm_img_list": "[]",
            "dm_img_str": "JK",
            "dm_cover_img_str": "AB",
            "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
        }, key)
        body = {
            "dyn_req": {
                "content": {"contents": [{"raw_text": text, "biz_id": "", "type": 1}]},
                "scene": 1,
                "meta": {"app_meta": {"from": "create.dynamic.web", "mobi_app": "web"}},
                "topic": {"id": int(topic_id)},
                "attach_card": None,
            }
        }
        self._json(self.http.post(
            self.API + "/x/dynamic/feed/create/dyn",
            headers={**self._headers(), "Content-Type": "application/json"},
            params={"csrf": self.settings.bili_jct, **{k: v for k, v in params.items() if k != "csrf"}},
            json=body,
            timeout=15,
        ))
        return True

    def post_dynamic(self, text: str, topic: str | int | None = None) -> bool:
        if self.settings.dry_run:
            self.last_write_simulated = True
            print(f"[DRY-RUN] 发布动态: {text}")
            return True
        self.last_write_simulated = False
        topic_id: int | None = None
        if topic is not None:
            try:
                topic_id = int(topic)
            except (TypeError, ValueError):
                topic_id = self.find_topic_id(str(topic))
            if not topic_id:
                raise BilibiliError(f"未找到 B 站话题“{topic}”，为避免发成普通搜索链接，本次未发布")
            return self._post_dynamic_with_topic(text, topic_id)
        payload = {
            "dynamic_id": 0, "type": 4, "rid": 0, "content": text,
            "up_choose_comment": 0, "up_close_comment": 0,
            "extension": '{"emoji_type":1,"from":{"emoji_type":1},"flag_cfg":{}}',
            "at_uids": "", "ctrl": "[]", "csrf_token": self.settings.bili_jct, "csrf": self.settings.bili_jct,
        }
        self._json(self.http.post("https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/create", headers=self._headers(), data=payload, timeout=15))
        return True
