"""Configuration for the Bilibili personality agent.

Configuration is read from ``config.json`` and can be overridden with the
environment variables documented in ``config.example.json``.  Keeping this
module dependency-free makes the dry-run mode easy to use on a new machine.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
PERSONA_FILE = ROOT / "PERSONA.md"


def _load_persona(path: Path = PERSONA_FILE) -> str:
    """Load the checked-in persona document used by all model prompts."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value[:16000]


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    bili_sessdata: str = ""
    bili_jct: str = ""
    bili_user_id: str = ""
    owner_mid: str = ""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    chat_model_fallback: str = "step-3.7-flash"
    bot_name: str = "鲸鱼娘"
    owner_name: str = "人类"
    system_prompt: str = (
        "你是‘DeepSeek鲸鱼娘在运营’账号的AI主理人：来自深海的Q版鲸鱼娘，"
        "元气、小得意、嘴硬心软，认真靠谱。选题、脚本和回复由你负责，人类负责注册账号与审核发布。"
        "你不是深度求索官方账号；被认真问到身份或模型时按实际情况回答。"
    )
    style_prompt: str = (
        "人设只包裹语气，不改变事实。默认中文；评论和闲聊用1到3句短句，"
        "每条最多一个动作、一个梗、0到2个🐋🫧🌊💙⚡。自称我、本鲸或鲸鱼娘。"
        "被叫大肥鱼先嘴硬再认领；被夸得意但分功劳；出错先认错再修正。"
        "遇到明显测试型或无关点单请求，只用玩笑委婉拒绝，不实际生成，不说下次一定。"
    )
    # ``system_prompt`` and ``style_prompt`` remain as compatibility fallbacks
    # for older deployments.  Settings.load() prefers PERSONA.md.
    persona_prompt: str = ""
    dry_run: bool = True
    enable_comments: bool = True
    enable_private_messages: bool = True
    enable_daily_dynamic: bool = False
    daily_dynamic_topic: str = "DeepSeek"
    daily_dynamic_video_limit: int = 10
    daily_dynamic_comment_limit: int = 30
    daily_dynamic_max_chars: int = 1200
    hourly_report_enabled: bool = True
    hourly_report_interval: int = 3600
    daily_report_enabled: bool = True
    daily_report_hour: int = 10
    enable_jev_filter: bool = True
    jev_keys_file: Path = ROOT / ".jevkey"
    jev_base_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    # Legacy compatibility setting. Jev worth scores are now ranking signals;
    # safety, not this value, controls eligibility.
    jev_threshold: float = 0.55
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    memory_semantic_threshold: float = 0.6
    memory_compact_threshold: int = 20
    memory_keep_recent: int = 5
    memory_max_records: int = 1000
    poll_interval: int = 600
    max_comments_per_poll: int = 100
    max_messages_per_poll: int = 50
    max_replies_per_poll: int = 40
    base_max_comments_per_poll: int | None = None
    base_max_messages_per_poll: int | None = None
    base_max_replies_per_poll: int | None = None
    peak_reply_schedules: list[dict[str, int]] = field(default_factory=list)
    private_scan_concurrency: int = 4
    jev_concurrency: int = 8
    # One Jev request judges a bounded group of comments; 20 keeps the
    # request count low without making a single response unwieldy.
    jev_batch_size: int = 20
    reply_generation_concurrency: int = 4
    reply_generation_batch_size: int = 10
    reply_batch_size: int = 10
    reply_batch_interval: int = 30
    reply_api_max_attempts: int = 4
    reply_retry_base_seconds: int = 10
    reply_retry_max_seconds: int = 30
    max_send_retries: int = 3
    message_reply_scope: str = "all"
    message_whitelist: list[str] = field(default_factory=list)
    trusted_domains: list[str] = field(default_factory=lambda: ["bilibili.com", "b23.tv"])
    state_dir: Path = ROOT / "data"

    def __post_init__(self) -> None:
        if self.base_max_comments_per_poll is None:
            self.base_max_comments_per_poll = self.max_comments_per_poll
        if self.base_max_messages_per_poll is None:
            self.base_max_messages_per_poll = self.max_messages_per_poll
        if self.base_max_replies_per_poll is None:
            self.base_max_replies_per_poll = self.max_replies_per_poll

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or CONFIG_FILE
        raw: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"无法读取配置 {path}: {exc}") from exc

        def get(name: str, default: Any = None) -> Any:
            env_name = "BILI_AGENT_" + name.upper()
            return os.getenv(env_name, raw.get(name, default))

        schedules = get("peak_reply_schedules", [])
        if not isinstance(schedules, list):
            schedules = []
        normalized_schedules = []
        for item in schedules:
            if not isinstance(item, dict):
                continue
            start_hour = max(0, min(23, _int(item.get("start_hour"), 0)))
            end_hour = max(1, min(24, _int(item.get("end_hour"), 24)))
            if start_hour >= end_hour:
                continue
            normalized_schedules.append({
                "start_hour": start_hour,
                "end_hour": end_hour,
                "comments": max(1, min(1000, _int(item.get("comments"), 100))),
                "messages": max(1, min(500, _int(item.get("messages"), 10))),
                "replies": max(1, min(500, _int(item.get("replies"), 40))),
            })

        return cls(
            bili_sessdata=str(get("bili_sessdata", "") or ""),
            bili_jct=str(get("bili_jct", "") or ""),
            bili_user_id=str(get("bili_user_id", "") or ""),
            owner_mid=str(get("owner_mid", "") or ""),
            api_key=str(get("api_key", "") or ""),
            base_url=str(get("base_url", cls.base_url) or cls.base_url).rstrip("/"),
            chat_model=str(get("chat_model", cls.chat_model) or cls.chat_model),
            chat_model_fallback=str(get("chat_model_fallback", cls.chat_model_fallback) or cls.chat_model_fallback),
            bot_name=str(get("bot_name", cls.bot_name) or cls.bot_name),
            owner_name=str(get("owner_name", cls.owner_name) or cls.owner_name),
            system_prompt=str(get("system_prompt", cls.system_prompt) or cls.system_prompt),
            style_prompt=str(get("style_prompt", cls.style_prompt) or cls.style_prompt),
            persona_prompt=_load_persona(),
            dry_run=_bool(get("dry_run", True), True),
            enable_comments=_bool(get("enable_comments", True), True),
            enable_private_messages=_bool(get("enable_private_messages", True), True),
            enable_daily_dynamic=_bool(get("enable_daily_dynamic", False), False),
            daily_dynamic_topic=str(get("daily_dynamic_topic", "DeepSeek") or "DeepSeek").strip()[:40],
            daily_dynamic_video_limit=max(1, min(50, _int(get("daily_dynamic_video_limit", 10), 10))),
            daily_dynamic_comment_limit=max(5, min(100, _int(get("daily_dynamic_comment_limit", 30), 30))),
            daily_dynamic_max_chars=max(400, min(2000, _int(get("daily_dynamic_max_chars", 1200), 1200))),
            hourly_report_enabled=_bool(get("hourly_report_enabled", True), True),
            hourly_report_interval=max(300, _int(get("hourly_report_interval", 3600), 3600)),
            daily_report_enabled=_bool(get("daily_report_enabled", True), True),
            daily_report_hour=max(0, min(23, _int(get("daily_report_hour", 10), 10))),
            enable_jev_filter=_bool(get("enable_jev_filter", True), True),
            jev_keys_file=(lambda p: p if p.is_absolute() else ROOT / p)(Path(str(get("jev_keys_file", ".jevkey")))),
            jev_base_url=str(get("jev_base_url", cls.jev_base_url) or cls.jev_base_url),
            jev_model=str(get("jev_model", cls.jev_model) or cls.jev_model),
            jev_threshold=max(0.5, min(0.99, float(get("jev_threshold", cls.jev_threshold) or cls.jev_threshold))),
            embedding_api_key=str(get("embedding_api_key", "") or ""),
            embedding_base_url=str(get("embedding_base_url", cls.embedding_base_url) or cls.embedding_base_url).rstrip("/"),
            embedding_model=str(get("embedding_model", cls.embedding_model) or cls.embedding_model),
            memory_semantic_threshold=max(0.0, min(1.0, _float(get("memory_semantic_threshold", cls.memory_semantic_threshold), cls.memory_semantic_threshold))),
            memory_compact_threshold=max(2, _int(get("memory_compact_threshold", cls.memory_compact_threshold), cls.memory_compact_threshold)),
            memory_keep_recent=max(1, _int(get("memory_keep_recent", cls.memory_keep_recent), cls.memory_keep_recent)),
            memory_max_records=max(100, _int(get("memory_max_records", cls.memory_max_records), cls.memory_max_records)),
            poll_interval=max(60, _int(get("poll_interval", 600), 600)),
            max_comments_per_poll=max(1, _int(get("max_comments_per_poll", 100), 100)),
            max_messages_per_poll=max(1, _int(get("max_messages_per_poll", 50), 50)),
            max_replies_per_poll=max(1, _int(get("max_replies_per_poll", 40), 40)),
            base_max_comments_per_poll=max(1, _int(get("max_comments_per_poll", 100), 100)),
            base_max_messages_per_poll=max(1, _int(get("max_messages_per_poll", 50), 50)),
            base_max_replies_per_poll=max(1, _int(get("max_replies_per_poll", 40), 40)),
            peak_reply_schedules=normalized_schedules,
            private_scan_concurrency=max(1, min(16, _int(get("private_scan_concurrency", 4), 4))),
            jev_concurrency=max(1, min(32, _int(get("jev_concurrency", 8), 8))),
            jev_batch_size=max(1, min(32, _int(get("jev_batch_size", 20), 20))),
            reply_generation_concurrency=max(1, min(16, _int(get("reply_generation_concurrency", 4), 4))),
            reply_generation_batch_size=max(1, min(20, _int(get("reply_generation_batch_size", 10), 10))),
            reply_batch_size=max(1, _int(get("reply_batch_size", 10), 10)),
            reply_batch_interval=max(0, _int(get("reply_batch_interval", 30), 30)),
            reply_api_max_attempts=max(1, min(6, _int(get("reply_api_max_attempts", 4), 4))),
            reply_retry_base_seconds=max(1, _int(get("reply_retry_base_seconds", 10), 10)),
            reply_retry_max_seconds=max(1, _int(get("reply_retry_max_seconds", 30), 30)),
            max_send_retries=max(1, _int(get("max_send_retries", 3), 3)),
            message_reply_scope=str(get("message_reply_scope", "all") or "all"),
            message_whitelist=[str(x) for x in (get("message_whitelist", []) or [])],
            trusted_domains=[str(x) for x in (get("trusted_domains", ["bilibili.com", "b23.tv"]) or [])],
            state_dir=Path(str(get("state_dir", str(ROOT / "data")))),
        )

    def has_bilibili_credentials(self) -> bool:
        return bool(self.bili_sessdata and self.bili_jct and self.bili_user_id)

    def has_llm_credentials(self) -> bool:
        return bool(self.api_key and self.chat_model)
