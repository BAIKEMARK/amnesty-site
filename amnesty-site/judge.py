"""判定一条评论是不是在「申请加入人类特赦名单」。

三层漏斗：
  层0 语境：同名内容下出现 >=N 条明确申请（strong），才把这条内容视为名单语境。
  层1 strong：赦免/特赦/铁券…或同音错字（特摄→特赦）/拼音命中 → 直接收。
  层2 intent：我也要/我我我/申请/加我…且必须带第一人称；veto 词（token/账号/资源）
        出现则整条丢弃——那是在申请别的东西。私信关掉语境关，直接进层3。
  层3 灰区：intent 命中的交给模型二分类。默认后端是 Jev（System One）：
        一个请求带一整批 noul 问题，每条评论问一次「作者是否在申请加入名单」，
        概率 >= 阈值（默认 0.45）就收；也支持 OpenAI 兼容模型（--judge llm）。
        模型拿到的上下文包含内容语境 + 前后邻居 + 渠道。

设计原则：宁可多收。模型不可用或超时，灰区一律放行，并把来源记成 rules。
"""
from __future__ import annotations

import json
import re
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

CONFIG_PATH = Path(__file__).with_name("keywords.json")
STRONG = "strong"
INTENT = "intent"
RULES = "rules"
LLM = "llm"
JEV = "jev"


def load_config(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip().lower()


def fix_homophones(text: str, table: dict[str, str]) -> str:
    result = normalize(text)
    for wrong, right in table.items():
        result = result.replace(normalize(wrong), normalize(right))
    return result


def pinyin_stream(text: str) -> str:
    """整段转无声调拼音，用于错字容错；没装 pypinyin 时返回空串。"""
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return ""
    try:
        return "".join(lazy_pinyin(str(text or ""), errors="ignore")).lower()
    except Exception:
        return ""


def classify(text: str, config: dict[str, Any]) -> tuple[str | None, str]:
    """返回 (层级, 命中词)。层级为 strong / intent / None。"""
    fixed = fix_homophones(text, config.get("homophone", {}))
    for term in config.get("strong", []):
        if normalize(term) and normalize(term) in fixed:
            return STRONG, term

    stream = pinyin_stream(text)
    if stream:
        for term in config.get("pinyin_terms", []):
            if term and term in stream:
                return STRONG, term

    for term in config.get("intent", []):
        key = normalize(term)
        if key and key in fixed:
            if term in IMPERSONAL_TERMS:
                return INTENT, term
            if any(normalize(person) in fixed for person in config.get("first_person", [])):
                return INTENT, term
    return None, ""


def is_noise(text: str, config: dict[str, Any]) -> bool:
    """整条只剩语气词/问号，没有任何申请线索。"""
    stripped = re.sub(r"[\s\W_]+", "", normalize(text))
    if not stripped:
        return True
    noise = "".join(re.sub(r"[\s\W_]+", "", normalize(word)) for word in config.get("noise_only", []))
    if not noise:
        return False
    residue = stripped
    for char in sorted(set(noise), key=len, reverse=True):
        residue = residue.replace(char, "")
    return not residue


def hit_veto(text: str, config: dict[str, Any]) -> str | None:
    """命中排除词：这条在申请别的东西（token/账号/资源），不是在申请名单。"""
    fixed = fix_homophones(text, config.get("homophone", {}))
    for term in config.get("veto", []):
        key = normalize(term)
        if key and key in fixed:
            return term
    stream = pinyin_stream(text)
    if stream:
        for term in config.get("veto_pinyin", []):
            if term and term in stream:
                return term
    return None


def content_key(row: dict[str, Any]) -> str:
    return str(row.get("内容ID") or row.get("内容链接") or "unknown")


def scope_of(rows: Sequence[dict[str, Any]], config: dict[str, Any]) -> tuple[set[str], dict[str, int]]:
    """内容级语境：同一条内容下明确申请够多，这条内容才算名单语境。"""
    hits: Counter[str] = Counter()
    for row in rows:
        level, _ = classify(str(row.get("评论内容") or ""), config)
        if level == STRONG:
            hits[content_key(row)] += 1
    threshold = int((config.get("scope") or {}).get("min_strong_hits", 3))
    return {key for key, count in hits.items() if count >= threshold}, dict(hits)


def neighbours(rows: Sequence[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """同内容下按时间排序，取每条评论的前后各一条作为语境。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(content_key(row), []).append(row)
    result: dict[str, tuple[str, str]] = {}
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: str(item.get("发表时间") or ""))
        for index, row in enumerate(ordered):
            before = str(ordered[index - 1].get("评论内容") or "")[:80] if index else ""
            after = str(ordered[index + 1].get("评论内容") or "")[:80] if index + 1 < len(ordered) else ""
            result[str(row.get("评论ID") or "")] = (before, after)
    return result


def content_hint(rows: Sequence[dict[str, Any]], key: str, config: dict[str, Any]) -> str:
    """给模型的语境：这条内容下已经有多少人在申请、他们怎么说的。"""
    same = [row for row in rows if content_key(row) == key]
    strong = [str(row.get("评论内容") or "") for row in same
              if classify(str(row.get("评论内容") or ""), config)[0] == STRONG]
    samples = " / ".join(dict.fromkeys(strong))[:160] if strong else ""
    return (
        f"该内容下共 {len(same)} 条评论，其中 {len(strong)} 条明确在申请加入名单。"
        + (f"其他人的原话示例：{samples}" if samples else "")
    )


BATCH_SIZE = 25

# 这些词本身即祈使，不需要第一人称也算申请。
IMPERSONAL_TERMS = {"申请", "报名", "排队", "+1", "+ 1"}

SYSTEM_PROMPT = """你在帮 B 站 UP 主整理一份《人类特赦名单》。
背景：UP 主发布名单公告，正文原话是「没找到自己的，评论區喊一声，我补进下一版」。
任务：判断每条评论的作者，是不是在要求把自己加进这份名单。

判定标准：
- 算：第一人称要名额（我也要 / 我我我 / 加上我 / 怎么没有我 / 申请 / 求带上）。跟风喊一嘴、语气随便都算。
- 不算：纯感叹、纯疑问、复读别人的梗、讨论剧情或完全无关话题、已经明确在名单里只表达感谢。
- 拿不准时判 true（活动口径宁可多收）。
- 部分条目来自私信：私信里直接开口要名额同样算。私信没有同帖语境是正常的，不要因为「看不到别人也在申请」就判 false。

只输出 JSON 数组，不要解释、不要代码块。格式：
[{"id":"评论ID","apply":true,"why":"不超过20字"}]"""


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    return cleaned[start:end + 1] if start >= 0 and end > start else "[]"


def llm_judge(
    items: list[dict[str, Any]],
    hints: dict[str, str],
    model,
    batch_size: int = BATCH_SIZE,
) -> dict[str, tuple[bool, str]]:
    """items: [{id,name,text,before,after,hint}]。返回 {id: (apply, why)}。"""
    verdicts: dict[str, tuple[bool, str]] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        payload = [
            {
                "id": item["id"],
                "昵称": item["name"],
                "评论": item["text"],
                "上一条": item["before"],
                "下一条": item["after"],
                "语境": item["hint"],
            }
            for item in batch
        ]
        user = (
            "下面是同一批待判定评论，每条都带所在内容的语境和前后邻居。\n"
            + json.dumps(payload, ensure_ascii=False, indent=1)
            + "\n请逐条判断并只输出 JSON 数组。"
        )
        try:
            response = model.chat.completions.create(
                model=model.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user}],
                temperature=0,
            )
            parsed = json.loads(_strip_fence(response.choices[0].message.content or "[]"))
        except Exception as exc:  # noqa: BLE001 - 模型挂了就走降级，不阻断抓取
            print(f"[判定] 模型调用失败，本批按多收处理：{type(exc).__name__}: {exc}")
            for item in batch:
                verdicts[item["id"]] = (True, "模型不可用，按多收放行")
            continue
        by_id = {str(entry.get("id")): entry for entry in parsed if isinstance(entry, dict)}
        for item in batch:
            entry = by_id.get(item["id"])
            if entry is None:
                verdicts[item["id"]] = (True, "模型未返回，按多收放行")
            else:
                verdicts[item["id"]] = (bool(entry.get("apply")), str(entry.get("why") or "")[:40])
    return verdicts


def build_model(settings):
    """复用项目已有的 OpenAI 兼容客户端配置。"""
    if not settings.has_llm_credentials():
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    class _Model:
        pass

    wrapper = _Model()
    wrapper.chat = OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                          timeout=60.0, max_retries=0).chat
    wrapper.model = settings.chat_model
    return wrapper


# ---------------------------------------------------------------- Jev 后端

JEV_STATE_PROJECT = (
    "A Bilibili creator runs a fan activity called the Human Amnesty List. The creator "
    "pinned an announcement saying: if you cannot find your name on the list, shout in "
    "the comments and you will be added in the next version. We are triaging newly "
    "collected comments and private messages to decide which authors are asking to be "
    "added to that list."
)
JEV_CRITERIA_TRUE = (
    "True: the author is asking for their own name to be added to the list. Includes "
    "first-person requests (I also want one / add me / how come I am not on it / count me in / "
    "applying for it), silly or follow-along requests, and direct asks inside private "
    "messages. Long or theatrical pleas count too: a multi-paragraph address to the creator, "
    "'dear great whale' style role-play, a mock petition, jokes about being put on trial or "
    "executed, or a story that ends in begging for pardon or mercy. A pledge of loyalty or a "
    "pre-emptive plea for mercy also counts: swearing devotion to the creator, asking not to "
    "be purged or judged once the AI becomes conscious, or registering oneself for future "
    "pardon, even when the text never literally says 'add me to the list'. Judge the intent "
    "of the whole text, not whether it sounds like a form application. When unsure, answer "
    "true: the activity prefers over-inclusion."
)
JEV_CRITERIA_FALSE = (
    "False: pure exclamations or questions, meme repetition, off-topic talk, thanks-only "
    "messages from people already on the list, and requests for OTHER things (API tokens, "
    "keys, accounts, invites, downloads, resources) even when they contain words like "
    "'apply' or 'I also want'."
)


def _jev_state_dir(preferred: Path) -> Path:
    """挑一个可写的状态目录：本地 data/ 被环境限制时退到临时目录。"""
    try:
        probe = preferred / ".write_probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return preferred
    except OSError:
        return Path(tempfile.mkdtemp(prefix="jev-state-"))


def build_jev(settings):
    """复用项目的 JevGate；环境变量里有 Key 时优先于 keys 文件（CI 用）。"""
    import os
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from jev import JevGate  # noqa: PLC0415

    env_keys = os.environ.get("TYPESAFE_API_KEYS") or os.environ.get("TYPESAFE_API_KEY") or ""
    keys = [part.strip() for part in re.split(r"[\n,;]+", env_keys) if part.strip()]
    if keys:
        scratch = Path(tempfile.mkdtemp(prefix="jev-amnesty-"))
        gate = JevGate(scratch / "keys.txt", scratch / "state.json",
                       settings.jev_base_url, settings.jev_model, settings.jev_threshold)
        gate.keys = keys
        gate._key_signature = lambda: "env"  # noqa: SLF001 - 环境注入的钥匙没有旧冷却要继承
        return gate
    state_dir = _jev_state_dir(Path(settings.state_dir))
    gate = JevGate(settings.jev_keys_file, state_dir / "jev_state.json",
                   settings.jev_base_url, settings.jev_model, settings.jev_threshold)
    return gate if gate.keys else None


def jev_judge(
    items: list[dict[str, Any]],
    gate,
    config: dict[str, Any],
) -> dict[str, tuple[bool, str]]:
    """items: [{id,channel,name,text,before,after,hint}]。Jev System One 批量 noul。

    一个请求带一整批问题（每条评论一个 noul），失败时本批按多收放行，
    与 llm_judge 的降级口径一致。
    """
    jev_cfg = config.get("jev") or {}
    threshold = float(jev_cfg.get("noul_threshold", 0.45))
    batch_size = max(1, int(jev_cfg.get("batch_size", 40)))
    verdicts: dict[str, tuple[bool, str]] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        questions: dict[str, Any] = {}
        entries = []
        for index, item in enumerate(batch):
            qid = f"q{start + index}"
            entries.append({
                "id": qid,
                "channel": item.get("channel") or "comment",
                "author": item.get("name") or "",
                "text": item.get("text") or "",
                "previous": item.get("before") or "",
                "next": item.get("after") or "",
                "context": item.get("hint") or "",
            })
            questions[qid] = {
                "type": "noul",
                "instructions": (
                    f"Is the author of item {qid} asking to be added to the amnesty list? "
                    "Answer for this item only."
                ),
                "criteria": {"true": JEV_CRITERIA_TRUE, "false": JEV_CRITERIA_FALSE},
            }
        state = {
            "project": JEV_STATE_PROJECT,
            "criteria": {"true": JEV_CRITERIA_TRUE, "false": JEV_CRITERIA_FALSE},
            "items": entries,
        }
        try:
            payload = gate._ask(state, questions)  # noqa: SLF001 - 复用钥匙轮换与重试
        except Exception as exc:  # noqa: BLE001 - Jev 挂了走降级，不阻断抓取
            print(f"[判定] Jev 调用失败，本批按多收处理：{type(exc).__name__}: {exc}")
            for item in batch:
                verdicts[item["id"]] = (True, "Jev 不可用，按多收放行")
            continue
        answers = payload.get("answers") or {}
        for index, item in enumerate(batch):
            answer = answers.get(f"q{start + index}") or {}
            probability = float(answer.get("noul") or 0.0)
            accept = probability >= threshold
            verdicts[item["id"]] = (accept, f"jev {probability:.2f}")
    return verdicts


def select(
    rows: Sequence[dict[str, Any]],
    config: dict[str, Any],
    mode: str = LLM,
    model=None,
    verbose: bool = True,
    *,
    require_scope: bool = True,
    context_hint: str = "",
    extra_scope: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """返回（收录的评论行，统计）。收录行带 matched_by / why 字段。

    ``require_scope=False`` 用于私信这类「一对一开口」的场合：没有同帖语境
    可以依靠，发信人本人说「我要」就已经构成申请，不该被语境关挡掉。
    ``extra_scope`` 是上一轮已经确认的名单内容：增量抓取时本批只有几十条，
    靠它才不会因为「这一批里凑不满 3 条明确申请」而把整帖判出语境。
    """
    excluded_names = {str(name) for name in config.get("author_names", [])}
    in_scope, strong_counts = scope_of(rows, config)
    in_scope |= {str(key) for key in extra_scope if str(key)}
    pair = neighbours(rows)
    stats = Counter()

    accepted: list[dict[str, Any]] = []
    gray: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("评论者昵称") or "")
        text = str(row.get("评论内容") or "")
        if name in excluded_names:
            stats["skipped_author"] += 1
            continue
        level, term = classify(text, config)
        if level == STRONG:
            accepted.append({**row, "matched_by": f"strong:{term}", "why": ""})
            stats["strong"] += 1
            continue
        if level != INTENT:
            stats["no_signal"] += 1
            continue
        veto = hit_veto(text, config)
        if veto:
            stats["veto"] += 1
            continue
        if require_scope and content_key(row) not in in_scope:
            stats["out_of_scope"] += 1
            continue
        if is_noise(text, config):
            stats["noise"] += 1
            continue
        before, after = pair.get(str(row.get("评论ID") or ""), ("", ""))
        gray.append({**row, "matched_by": f"intent:{term}", "why": "",
                     "before": before, "after": after})

    if gray and mode in (LLM, JEV) and model is None:
        if verbose:
            print(f"[判定] 没有可用的{'Jev' if mode == JEV else '模型'}，灰区按规则全部放行")
        mode = RULES

    if gray and mode in (LLM, JEV):
        present = {content_key(row) for row in rows}
        hints = {key: content_hint(rows, key, config) for key in in_scope if key in present}
        items = [{
            "id": str(row.get("评论ID") or f"row-{index}"),
            "channel": str(row.get("渠道") or ""),
            "name": str(row.get("评论者昵称") or ""),
            "text": str(row.get("评论内容") or ""),
            "before": row["before"], "after": row["after"],
            "hint": hints.get(content_key(row), context_hint),
        } for index, row in enumerate(gray)]
        verdicts = jev_judge(items, model, config) if mode == JEV else llm_judge(items, hints, model)
        for row in gray:
            rid = str(row.get("评论ID") or "")
            apply_flag, why = verdicts.get(rid, (True, "未判定，按多收放行"))
            if apply_flag:
                accepted.append({**row, "matched_by": "jev" if mode == JEV else "llm", "why": why})
                stats["llm_yes" if mode == LLM else "jev_yes"] += 1
            else:
                stats["llm_no" if mode == LLM else "jev_no"] += 1
                if verbose:
                    print(f"[判定] 排除 {row.get('评论者昵称')}：{row.get('评论内容')[:30]} → {why}")
    else:
        for row in gray:
            accepted.append({**row, "matched_by": "rules", "why": "灰区按多收放行"})
            stats["rules_gray"] += 1

    stats["accepted"] = len(accepted)
    return accepted, dict(stats)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import csv
    import sys

    parser = argparse.ArgumentParser(description="离线试跑评论判定")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--mode", choices=[RULES, LLM, JEV], default=RULES)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keywords", type=Path, default=CONFIG_PATH)
    args = parser.parse_args(argv)

    config = load_config(args.keywords)
    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.limit:
        rows = rows[:args.limit]

    model = None
    if args.mode in (LLM, JEV):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import Settings
        settings = Settings.load()
        model = build_jev(settings) if args.mode == JEV else build_model(settings)

    accepted, stats = select(rows, config, mode=args.mode, model=model)
    print(json.dumps(stats, ensure_ascii=False))
    for row in accepted:
        print(f"[{row['matched_by']}] {row.get('评论者昵称')}：{row.get('评论内容')}"
              + (f"  ({row['why']})" if row.get("why") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
