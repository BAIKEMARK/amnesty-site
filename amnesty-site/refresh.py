#!/usr/bin/env python3
"""抓 B 站评论与私信里申请赦免的人，合并进名册并重新打包站点。

用法：
    python amnesty-site/refresh.py --fetch                 # 增量：每个内容翻到上次水位就停
    python amnesty-site/refresh.py --fetch --full          # 全量重抓（约 70 分钟，每周对账用）
    python amnesty-site/refresh.py --fetch --no-private    # 本轮不抓私信
    python amnesty-site/refresh.py --source 某评论.csv     # 离线：导入已有 CSV
    python amnesty-site/refresh.py --fetch --dry-run       # 只报告会新增多少人，不写任何文件

水位与语境写在 site/crawl-state.json：水位只按根评论的时间推进，且只在
data.json 落盘成功之后才前进，所以中途失败下一轮会重抓同一段（靠 merge 去重），
不会漏也不会重复。失败时保留上一次的数据，只把 status.json 的 result 写成
failed，站点不会空白。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SITE_DIR = Path(__file__).resolve().parent
REPO_DIR = SITE_DIR.parent
SITE = SITE_DIR / "site"
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SITE_DIR))

import judge  # noqa: E402
from comment_batch import filter_comments, normalize_keywords  # noqa: E402
from comment_csv import read_reviewed, write_comments  # noqa: E402
from import_comments import load_data, merge_rows, output_payload  # noqa: E402

DATA_PATH = SITE / "data.json"
EXCLUDE_PATH = SITE / "exclude.json"
STATUS_PATH = SITE / "status.json"
CRAWL_STATE_PATH = SITE / "crawl-state.json"
PRIVATE_CHANNEL = "私信"
DEFAULT_KEYWORDS = ["赦免"]
CHINA_TIME = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(CHINA_TIME)


def load_exclude(path: Path = EXCLUDE_PATH) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(item) for item in payload]
    return [str(item) for item in payload.get("uids", [])]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_status(path: Path, **fields: Any) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            previous = {}
    payload = {**previous, **fields, "checkedAt": now().isoformat(timespec="seconds")}
    if payload.get("result") == "ok":
        payload["updatedAt"] = payload["checkedAt"]
    write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def fetch_rows(
    *,
    watermarks: dict[str, int] | None = None,
    thread_window_seconds: int = 86_400,
    private_window_minutes: int = 180,
    private_limit: int = 2000,
    include_private: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int] | None, dict[str, Any]]:
    """抓评论（可增量）+ 近期私信。返回（行, 新水位, 统计）。"""
    from bilibili import BilibiliClient, BilibiliError
    from config import Settings

    settings = Settings.load()
    # 读评论只要有登录态即可；bili_jct 是写操作的 csrf，抓取用不到。
    if not settings.bili_sessdata:
        raise BilibiliError("缺少 B 站凭据：至少需要 SESSDATA")

    def progress(channel: str, completed: int, total: int, count: int) -> None:
        print(f"[抓取] {channel} {completed}/{total}，累计 {count} 条评论", flush=True)

    client = BilibiliClient(settings)
    rows = client.export_owned_comments(
        progress=progress,
        watermarks=watermarks,
        thread_refresh_seconds=thread_window_seconds,
    )
    new_watermarks = dict(client.last_watermarks)
    meta: dict[str, Any] = {
        "incremental": watermarks is not None,
        "commentRows": len(rows),
        "changedContents": client.last_watermark_updates,
    }
    truncations = [info for info in client.last_truncations.values() if info.get("kind") == "content"]
    if truncations:
        meta["truncatedContents"] = len(truncations)
        meta["truncatedList"] = truncations
        lost = sum(max(0, int(i.get("declared") or 0) - int(i.get("got") or 0)) for i in truncations)
        meta["truncatedMissing"] = lost
        print(f"[抓取] {len(truncations)} 个内容撞上平台分页上限，接口最多只给到这里（合计差 {lost} 条）")
        for info in truncations:
            print(f"        {info.get('channel')} {info.get('oid')}: 拿到 {info.get('got')} / 声明 {info.get('declared')}")
    print(f"[抓取] 本轮拿到 {len(rows)} 条评论，水位有更新的内容 {client.last_watermark_updates} 个")

    if include_private and settings.bili_user_id:
        try:
            private = client.export_private_messages(
                since_minutes=private_window_minutes, limit=private_limit
            )
            print(f"[私信] 近 {private_window_minutes} 分钟收到 {len(private)} 条文字私信")
            rows.extend(private)
            meta["privateMessages"] = len(private)
        except Exception as exc:  # noqa: BLE001 - 私信挂了不该让整轮评论作废
            message = f"{type(exc).__name__}: {exc}"
            print(f"[私信] 抓取失败，本轮跳过：{message}", file=sys.stderr)
            meta["privateError"] = message
    return rows, new_watermarks, meta


def judge_rows(
    rows: list[dict[str, Any]],
    keywords: list[str],
    mode: str,
    config_path: Path | None,
    *,
    extra_scope: Iterable[str] = (),
    rejected_out: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """按选定口径筛出「在申请加入名单」的评论；同时返回确认过的名单内容键。"""
    if mode == "words":
        return filter_comments(rows, keywords), set()
    from config import Settings

    import judge

    config = judge.load_config(config_path or judge.CONFIG_PATH)
    settings = Settings.load()
    if mode == "jev":
        model = judge.build_jev(settings)
    elif mode == "llm":
        model = judge.build_model(settings)
    else:
        model = None
    public = [row for row in rows if str(row.get("渠道") or "") != PRIVATE_CHANNEL]
    private = [row for row in rows if str(row.get("渠道") or "") == PRIVATE_CHANNEL]

    accepted, stats = judge.select(public, config, mode=mode, model=model,
                                   extra_scope=extra_scope, rejected=rejected_out)
    scope, _ = judge.scope_of(public, config)
    known_scope = {str(key) for key in extra_scope if str(key)} | scope

    if private:
        extra, private_stats = judge.select(
            private, config, mode=mode, model=model,
            require_scope=False,
            context_hint="这是一条私信：发信人单独对 UP 主说，没有同帖语境。",
            rejected=rejected_out,
        )
        accepted.extend(extra)
        stats.update({f"private_{key}": value for key, value in private_stats.items()})
    print(f"判定统计：{stats}")
    return accepted, known_scope


def load_builder(site: Path):
    """按目录加载站点自己的 build.py，--site-dir 指向副本时也能正确打包。"""
    import importlib.util

    target = site / "build.py"
    spec = importlib.util.spec_from_file_location("amnesty_site_build", target)
    if spec is None or spec.loader is None:
        raise SystemExit(f"找不到 {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="刷新赦免名册数据并重新打包站点")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fetch", action="store_true", help="在线抓取账号投稿和动态评论")
    source.add_argument("--source", type=Path, help="已有评论 CSV；不联网")
    parser.add_argument("--keyword", action="append", default=None, help="申请关键词，可重复；默认：赦免")
    parser.add_argument("--judge", choices=["jev", "llm", "rules", "words"], default="jev",
                        help="判定口径：jev=规则+同音+Jev 批量判灰区（默认）；llm=OpenAI 兼容模型；rules=灰区全收；words=旧的纯关键词")
    parser.add_argument("--keywords", type=Path, help="判定词表路径（默认 amnesty-site/keywords.json）")
    parser.add_argument("--dry-run", action="store_true", help="只报告差异，不写文件")
    parser.add_argument("--full", action="store_true",
                        help="忽略水位做全量重抓（约 68 分钟）。默认增量：翻到上次水位就停")
    parser.add_argument("--thread-window-hours", type=float, default=24,
                        help="增量时，水位之前多少小时内仍重扫楼中楼（默认 24 小时）")
    parser.add_argument("--private-window-minutes", type=int, default=180,
                        help="只扫最近这么多分钟内有过消息的私信会话（默认 180）")
    parser.add_argument("--private-limit", type=int, default=2000,
                        help="私信单轮最多取多少条文字消息（默认 2000）")
    parser.add_argument("--no-private", action="store_true", help="本轮不抓私信")
    parser.add_argument("--no-avatars", action="store_true", help="跳过头像补全")
    parser.add_argument("--standalone", action="store_true", help="同时生成离线单文件版")
    parser.add_argument("--site-dir", type=Path, default=SITE, help=f"站点目录（默认：{SITE}）")
    parser.add_argument("--csv-out", type=Path, help="可选：另存本次命中的评论明细")
    args = parser.parse_args(argv)

    site = args.site_dir.resolve()
    data_path = site / "data.json"
    status_path = site / "status.json"
    state_path = site / "crawl-state.json"
    keywords = normalize_keywords(args.keyword if args.keyword is not None else DEFAULT_KEYWORDS)
    excluded = load_exclude(site / "exclude.json")
    started = now()

    crawl_state = load_state(state_path)
    known_scope = [str(key) for key in (crawl_state.get("scope") or [])]
    new_watermarks: dict[str, int] | None = None
    meta: dict[str, Any] = {}

    try:
        if args.fetch:
            watermarks = {} if args.full else {
                str(key): int(value or 0)
                for key, value in (crawl_state.get("contents") or {}).items()
            }
            rows, new_watermarks, meta = fetch_rows(
                watermarks=watermarks,
                thread_window_seconds=int(args.thread_window_hours * 3600),
                private_window_minutes=args.private_window_minutes,
                private_limit=args.private_limit,
                include_private=not args.no_private,
            )
        else:
            rows = read_reviewed(args.source)
    except Exception as exc:  # noqa: BLE001 - 任何抓取失败都只记录，不破坏现有数据
        message = f"{type(exc).__name__}: {exc}"
        print(f"抓取失败，保留现有数据：{message}", file=sys.stderr)
        if not args.dry_run:
            write_status(status_path, result="failed", lastError=message)
        return 1

    rejected: list[dict[str, Any]] = []
    matched, scope = judge_rows(
        rows, keywords, args.judge, args.keywords, extra_scope=known_scope,
        rejected_out=rejected,
    )
    if rejected and not args.dry_run:
        # 被拒明细落盘：调判据时直接读这份本地文件重判，不用重抓。
        write_atomic(site / "rejected.json", json.dumps(
            {"updatedAt": now().isoformat(timespec="seconds"), "rows": rejected},
            ensure_ascii=False, indent=1) + "\n")
        print(f"被拒 {len(rejected)} 条已写入 {site / 'rejected.json'}（可复核/重判）")
    data, stats = merge_rows(matched, load_data(data_path), excluded)
    print(
        f"命中评论 {len(matched)} 条；名单 {stats['people']} 人"
        f"（本次新增 {stats['addedPeople']} 人 / {stats['addedComments']} 条），"
        f"排除命中 {stats['skippedExcluded']} 条"
    )

    if args.dry_run:
        return 0

    data["version"] = started.strftime("%Y-%m-%d")
    write_atomic(data_path, json.dumps(output_payload(data), ensure_ascii=False, separators=(",", ":")))

    # 水位和语境只在名册落盘之后才前进：中途失败时下一轮还会重抓同一段，
    # 靠 merge_rows 去重，不会漏也不会重复。
    merged_scope = sorted({str(key) for key in known_scope} | {str(key) for key in scope})
    contents = new_watermarks if new_watermarks is not None else dict(crawl_state.get("contents") or {})
    if contents or merged_scope:
        write_atomic(state_path, json.dumps({
            "version": 1,
            "updatedAt": now().isoformat(timespec="seconds"),
            "contents": contents,
            "scope": merged_scope,
        }, ensure_ascii=False, indent=2) + "\n")

    if args.csv_out:
        write_comments(args.csv_out, matched)

    if not args.no_avatars:
        from config import Settings
        from fetch_avatars import sync_avatars

        # 头像只是外观，任何失败都不该拦住数据落盘与重新打包。
        try:
            # 只取外链 URL，不下载图片；批量接口一次 50 个 UID，需要登录态才能用。
            _, failures = sync_avatars(
                data["people"],
                cache_path=site / "avatars.json",
                sessdata=Settings.load().bili_sessdata,
            )
            if failures:
                print(f"头像补全有 {failures} 个失败，下次会重试")
        except Exception as exc:  # noqa: BLE001
            print(f"[头像] 本轮跳过：{type(exc).__name__}: {exc}")

    builder = load_builder(site)
    # 站点挂在 /amnesty/ 子路径下，根目录留给门户页（以后加别的子站）。
    builder.build(standalone=False, out=site / "dist", subdir="amnesty")
    builder.write_portal(site / "dist")
    if args.standalone:
        builder.build(standalone=True, out=site / "dist-standalone")
    write_status(
        status_path,
        result="ok",
        people=stats["people"],
        comments=stats["comments"],
        addedPeople=stats["addedPeople"],
        addedComments=stats["addedComments"],
        excluded=len(excluded),
        source="fetch" if args.fetch else "csv",
        keywords=keywords,
        **meta,
        durationSeconds=round((now() - started).total_seconds(), 1),
    )
    print(f"已更新：{data_path}，站点已重新打包到 {site / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
