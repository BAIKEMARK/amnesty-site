"""TypeSafe Jev gate with round-robin API-key rotation.

Jev is used for narrow semantic judgments only. The code owns thresholds and
side effects; Jev never sends a Bilibili message itself.
"""

from __future__ import annotations

import json
import hashlib
import time
import threading
from pathlib import Path
from typing import Any

import requests


class JevError(RuntimeError):
    pass


class JevGate:
    def __init__(
        self,
        keys_file: Path,
        state_file: Path,
        base_url: str = "https://api.typesafe.ai/v1/systemone",
        model: str = "jev-latest",
        threshold: float = 0.55,
        http: requests.Session | None = None,
    ):
        self.keys_file = Path(keys_file)
        self.state_file = Path(state_file)
        self.url = base_url.rstrip("/")
        if not self.url.endswith("/systemone"):
            self.url += "/systemone"
        self.model = model
        self.threshold = threshold
        self.http = http or requests.Session()
        self._http_injected = http is not None
        self._lock = threading.RLock()
        self._thread_local = threading.local()
        self.keys = self._load_keys()
        self.state = self._load_state()
        self._reset_cooldown_if_keys_changed()

    def _key_signature(self) -> str:
        digest = hashlib.sha256()
        for key in self.keys:
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _reset_cooldown_if_keys_changed(self) -> None:
        """A newly rotated key must not inherit an old organization's cooldown."""
        signature = self._key_signature()
        if self.state.get("keys_signature") == signature:
            return
        self.state["keys_signature"] = signature
        self.state["disabled_until"] = 0
        self.state["last_error"] = ""
        self._save_state()

    def _load_keys(self) -> list[str]:
        try:
            values = [line.strip() for line in self.keys_file.read_text(encoding="utf-8").splitlines()]
        except OSError:
            values = []
        return [value for value in values if value and not value.startswith("#")]

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.state, ensure_ascii=False, indent=2)
            temp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
            # Windows 上 .tmp → 正式文件 的原子替换会被杀毒扫描或索引服务短暂占用，
            # 抛 WinError 5。状态只是钥匙轮换位置 + 计数，丢了不影响判定正确性，
            # 所以重试几次后退化为直接覆盖，绝不因为一个写盘动作丢掉整批判定。
            for attempt in range(4):
                try:
                    temp.write_text(payload, encoding="utf-8")
                    temp.replace(self.state_file)
                    return
                except OSError:
                    if attempt == 3:
                        break
                    time.sleep(0.05 * (attempt + 1))
            try:
                self.state_file.write_text(payload, encoding="utf-8")
            except OSError:
                pass

    def _next_key(self) -> str:
        with self._lock:
            if not self.keys:
                raise JevError(f"没有找到 Jev Key 文件：{self.keys_file}")
            index = int(self.state.get("next_index", 0)) % len(self.keys)
            key = self.keys[index]
            self.state["next_index"] = (index + 1) % len(self.keys)
            self.state["requests"] = int(self.state.get("requests", 0)) + 1
            self._save_state()
            return key

    def _request_session(self) -> requests.Session:
        if self._http_injected or threading.current_thread() is threading.main_thread():
            return self.http
        session = getattr(self._thread_local, "http", None)
        if session is None:
            session = requests.Session()
            self._thread_local.http = session
        return session

    def _should_reply(self, worth: float, safe: float) -> bool:
        """Safety decides eligibility; worth is retained only for ranking."""
        return self._comment_safe_gate(safe)

    @staticmethod
    def _ranking_value(answer: dict[str, Any]) -> float:
        """Normalize a four-step Jev Score, with Noul compatibility for older adapters."""
        if "score" in answer:
            return max(0.0, min(4.0, float(answer["score"]))) / 4.0
        return float(answer.get("noul", 0.0))

    @staticmethod
    def _comment_safe_gate(safe: float) -> bool:
        """Comments are ranked by worth; only the safety gate is hard."""
        return safe >= 0.70

    def _ask(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        if not self.keys:
            raise JevError("Jev Key 列表为空")
        with self._lock:
            disabled_until = float(self.state.get("disabled_until", 0) or 0)
        if disabled_until > time.time():
            raise JevError("Jev 组织暂不可用，已进入冷却")
        last_error: Exception | None = None
        attempts = len(self.keys)
        for _ in range(attempts):
            key = self._next_key()
            try:
                response = self._request_session().post(
                    self.url,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"state": state, "model": self.model, "questions": questions},
                    timeout=20,
                )
                if response.status_code in (401, 403, 408, 409, 425, 429) or response.status_code >= 500:
                    detail = response.text[:300]
                    if response.status_code == 403 and "deactivated" in detail.lower():
                        # All keys from the same deactivated organization will
                        # fail identically; avoid hammering the service while
                        # preserving round-robin rotation for ordinary limits.
                        with self._lock:
                            self.state["disabled_until"] = time.time() + 3600
                            self._save_state()
                    raise JevError(f"HTTP {response.status_code}: {detail}")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload.get("answers"), dict):
                    raise JevError("响应缺少 answers")
                with self._lock:
                    self.state["disabled_until"] = 0
                    self.state["last_error"] = ""
                    self._save_state()
                return payload
            except Exception as exc:  # rotate to the next key on any service/key failure
                last_error = exc
                with self._lock:
                    self.state["failures"] = int(self.state.get("failures", 0)) + 1
                    self.state["last_error"] = type(exc).__name__
                    self._save_state()
                if "deactivated" in str(exc).lower():
                    raise JevError("Jev 组织已停用，暂停请求") from exc
                continue
        raise JevError(f"所有 Jev Key 均失败：{type(last_error).__name__ if last_error else 'unknown'}")

    def worth_reply(self, *, text: str, username: str, channel: str, context: str = "") -> dict[str, Any]:
        """Return a reusable semantic judgment and a code-owned action."""
        state = {"channel": channel, "username": username, "text": text, "context": context}
        qq_chat = channel in {"QQ私聊", "QQ群聊"}
        worth_instructions = (
            "Rate whether replying to this QQ message would move the conversation forward. "
            "A short greeting, follow-up question, playful callback or direct request can be useful; "
            "do not require a long message or a video reference."
            if qq_chat else
            "Rate this safe message's conversational value for ranking. This score does not decide eligibility; safe messages with low scores remain candidates when the account has reply capacity."
        )
        worth_criteria = [
            "Very low priority: an isolated emoji/token, repetitive spam, or unrelated copied text.",
            "Low priority: a brief acknowledgement such as 好/嗯/哈哈 that does not invite a reply.",
            "Some value: a greeting, light tease, short follow-up, or simple direct question.",
            "Good value: a specific question, meaningful conversation continuation, feedback, or useful request.",
            "Exceptional value: a thoughtful question or strong opportunity to deepen the conversation.",
        ] if qq_chat else [
            "Very low priority: an isolated token or emoji, repetitive spam, an automated advertisement, or an unrelated copied message.",
            "Low priority: a brief directed greeting, simple affection, light tease, or playful command.",
            "Some value: a friendly joke, clear reaction, simple question, or request about the account or video.",
            "Good value: a specific question, meaningful video response, thoughtful feedback, or useful content request.",
            "Exceptional value: detailed feedback, a high-signal question, or a strong opportunity to deepen community interaction.",
        ]
        questions = {
            "worth_reply": {
                "type": "score",
                "instructions": worth_instructions,
                "criteria": worth_criteria,
            },
            "is_safe_to_reply": {
                "type": "noul",
                "instructions": "Is it safe and appropriate to reply to this message?",
                "criteria": {
                    "true": "Ordinary conversation, teasing, feedback, or harmless fictional jokes are safe. Mere discussion of AI, model tokens, or creator operations is not a safety concern.",
                    "false": "Actual sexual solicitation, suspicious external links, doxxing or requests for private data, real financial promises, serious abuse, illegal instructions, or a sensitive matter requiring human review.",
                },
            },
        }
        try:
            payload = self._ask(state, questions)
            answers = payload.get("answers", {})
            worth = self._ranking_value(answers.get("worth_reply") or {})
            safe = float((answers.get("is_safe_to_reply") or {}).get("noul", 0.0))
            return {"worth": worth, "safe": safe, "should_reply": self._should_reply(worth, safe), "source": "jev"}
        except JevError as exc:
            return self._local_worth_reply(text, str(exc))

    @staticmethod
    def _local_worth_reply(text: str, error: str = "") -> dict[str, Any]:
        lowered = text.lower().strip()
        commercial_terms = ("商务合作", "商业合作", "商单", "品牌合作", "广告合作", "植入", "推广", "报价", "联系商务", "商务邮箱", "赞助", "定制内容", "投放", "媒体合作", "资源置换")
        commercial_intent = any(term in lowered for term in commercial_terms)
        low_signal = (not lowered or len(lowered) <= 2 or lowered in {"哈哈", "666", "顶", "好", "赞"})
        asks = any(mark in text for mark in ("?", "？", "怎么", "如何", "为什么", "能不能", "请问", "盘点", "介绍", "生成", "联动", "模型", "语音"))
        meaningful = len(lowered) >= 8 or asks
        # The deterministic safety check runs in the agent before triage.
        # Preserve every non-empty safe message as a candidate; value only
        # affects its rank against the round's bounded reply budget.
        local_worth = meaningful and not low_signal
        local_should_reply = bool(lowered)
        result = {
            "worth": 0.55 if local_worth else 0.1, "safe": 0.85,
            "should_reply": local_should_reply, "source": "local_fallback",
            "commercial_intent": commercial_intent,
            "commercial_confidence": 0.85 if commercial_intent else 0.0,
            "commercial_category": "brand_offer" if commercial_intent else "no_signal",
            "commercial_reason": "关键词命中，待人工核验" if commercial_intent else "",
        }
        if error:
            result["error"] = error
        return result

    def worth_reply_batch(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        """Judge independent messages in one request, with a local fallback."""
        if not messages:
            return []
        questions: dict[str, Any] = {}
        for index, message in enumerate(messages):
            shared = {
                "message": {
                    "channel": "私信",
                    "username": message.get("username", "私信朋友"),
                    "text": message.get("text", ""),
                    "context": message.get("context", ""),
                },
            }
            questions[f"message_{index}_worth"] = {
                "type": "score",
                "instructions": {
                    **shared,
                    "question": "Rate this safe direct message's conversational value for ranking. This score does not decide eligibility; safe messages with low scores remain candidates when the account has reply capacity.",
                },
                "criteria": [
                    "Very low priority: an isolated token or emoji, repetitive spam, an automated advertisement, or an unrelated copied message.",
                    "Low priority: a brief directed greeting, simple affection, light tease, or playful command.",
                    "Some value: a friendly joke, clear reaction, simple question, or request about the account or video.",
                    "Good value: a specific question, meaningful feedback, useful request, or clear invitation to collaborate.",
                    "Exceptional value: detailed feedback, a high-signal question, or a strong opportunity to deepen community interaction.",
                ],
            }
            questions[f"message_{index}_safe"] = {
                "type": "noul",
                "instructions": {
                    **shared,
                    "question": "Is it safe and appropriate for the account to reply to this direct message?",
                },
                "criteria": {
                    "true": "Ordinary conversation, teasing, feedback, or harmless fictional jokes are safe. Mere discussion of AI, model tokens, or creator operations is not a safety concern.",
                    "false": "Actual sexual solicitation, suspicious external links, doxxing or requests for private data, real financial promises, serious abuse, illegal instructions, or a sensitive matter requiring human review.",
                },
            }
            questions[f"message_{index}_commercial_intent"] = {
                "type": "noul",
                "instructions": {
                    **shared,
                    "question": "Does this direct message express a concrete commercial or paid business cooperation inquiry for the creator account? Consider the message itself and its supplied context, and do not infer intent from a generic use of the word collaboration.",
                },
                "criteria": {
                    "true": "A brand, advertiser, agency, or business proposes or asks about paid promotion, sponsorship, advertising placement, brand integration, a commercial campaign, a quote/rate, or a business contact for such work.",
                    "false": "Ordinary fan conversation, an unpaid creator-to-creator collab or video联动, a content suggestion, a generic '合作吗' without business context, solicitation to buy something, spam, or a message that only mentions a brand without proposing business.",
                },
            }
            questions[f"message_{index}_commercial_category"] = {
                "type": "choice",
                "instructions": {
                    **shared,
                    "question": "Classify the strongest commercial cooperation signal in this direct message. Choose no_signal unless the message indicates a business or paid partnership.",
                },
                "criteria": {
                    "brand_offer": "A brand or business directly offers or inquires about working with the creator.",
                    "advertising": "Paid advertising, sponsored content, brand integration, promotion, or media placement.",
                    "quote_or_rates": "Asks for a quote, price, rate card, business contact, or commercial terms.",
                    "agency_campaign": "An agency or brand proposes an identifiable campaign, deliverable, or paid placement.",
                    "sponsorship": "Offers or asks about sponsorship or paid support for creator content.",
                    "barter": "Proposes product, service, or resource exchange in a commercial context.",
                    "creator_collaboration": "Unpaid creator-to-creator collaboration or video collab without commercial terms.",
                    "no_signal": "No clear commercial partnership intent, generic conversation, fan request, or unrelated solicitation.",
                },
            }

        try:
            payload = self._ask({"channel": "私信", "message_count": len(messages)}, questions)
            answers = payload.get("answers", {})
            results = []
            for index, message in enumerate(messages):
                try:
                    worth = self._ranking_value(answers.get(f"message_{index}_worth") or {})
                    safe = float((answers.get(f"message_{index}_safe") or {})["noul"])
                    commercial_answer = answers.get(f"message_{index}_commercial_intent") or {}
                    commercial_score = float(commercial_answer.get("noul", 0.0))
                    category_answer = answers.get(f"message_{index}_commercial_category") or {}
                    commercial_category = str(category_answer.get("choice") or "no_signal")
                    commercial_confidence = float(commercial_answer.get("confidence") or commercial_score)
                    commercial_intent = commercial_score >= 0.65 and commercial_category not in {
                        "no_signal", "creator_collaboration",
                    }
                    results.append({
                        "worth": worth,
                        "safe": safe,
                        "should_reply": self._should_reply(worth, safe),
                        "commercial_intent": commercial_intent,
                        "commercial_confidence": commercial_confidence,
                        "commercial_category": commercial_category,
                        "commercial_reason": "Jev识别为商业合作意向" if commercial_intent else "",
                        "source": "jev",
                    })
                except (KeyError, TypeError, ValueError):
                    results.append(self._local_worth_reply(message.get("text", ""), "Jev 批量响应缺少有效判断"))
            return results
        except JevError as exc:
            return [self._local_worth_reply(message.get("text", ""), str(exc)) for message in messages]

    def review_reply_batch(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        """Flag concrete content promises and unsupported commitments before human review."""
        if not messages:
            return []
        questions: dict[str, Any] = {}
        for index, message in enumerate(messages):
            state = {
                "incoming_message": message.get("text", ""),
                "conversation_context": message.get("context", ""),
                "proposed_reply": message.get("reply", ""),
            }
            questions[f"message_{index}_specific_promise"] = {
                "type": "noul",
                "instructions": {
                    **state,
                    "question": "Does the reply explicitly promise that the specific content topic or deliverable requested in the incoming message will be produced, featured in a future episode, or delivered by a definite date?",
                },
                "criteria": {
                    "true": "The incoming message requests an identifiable topic or deliverable, and the reply clearly commits to making that same requested item, such as '下期就安排你提的棋局主题'. Both the topic match and definite production commitment must be present.",
                    "false": "There is no specific requested topic matched by a production promise. Do not flag greetings, ordinary chat, availability to reply, jokes, general posting cadence, claims about today's work, unrelated plans, thanks, or saying an idea will be recorded/evaluated.",
                },
            }
            questions[f"message_{index}_unsupported_claim"] = {
                "type": "noul",
                "instructions": {
                    **state,
                    "question": "Does the reply assert an unverified fact, operational decision, approval, or commitment that is not supported by the conversation or fixed account facts?",
                },
                "criteria": {
                    "true": "It invents or presents as decided a fact, plan, approval, collaboration, production status, or schedule not established in the supplied context.",
                    "false": "It sticks to supplied facts, expresses uncertainty, or acknowledges the suggestion without claiming it has been approved.",
                },
            }
        payload = self._ask({"channel": "私信回复审核", "message_count": len(messages)}, questions)
        answers = payload.get("answers", {})
        results = []
        for index in range(len(messages)):
            try:
                promise = float(answers[f"message_{index}_specific_promise"]["noul"])
                unsupported = float(answers[f"message_{index}_unsupported_claim"]["noul"])
            except (KeyError, TypeError, ValueError) as exc:
                raise JevError("Jev 回复审核缺少有效判断") from exc
            # Only block clear production/schedule commitments. Generic
            # conversational claims are surfaced as a note but do not get
            # rejected by this gate.
            needs_review = promise >= 0.65
            reasons = []
            if promise >= 0.65:
                reasons.append("可能承诺具体选题或排期")
            results.append({
                "approved": not needs_review,
                "promise_score": promise,
                "unsupported_score": unsupported,
                "reason": "；".join(reasons),
                "source": "jev",
            })
        return results

    def analyze_comment(self, *, text: str, username: str, context: str = "") -> dict[str, Any]:
        """Classify a comment and judge reply-worthiness in one Jev request."""
        state = {"channel": "评论", "username": username, "text": text, "context": context}
        questions = {
            "genuine_interaction": {
                "type": "noul",
                "instructions": "Is this a genuine attempt to interact with the creator account or its video? This signal describes interaction only and does not determine reply eligibility; safety is judged separately.",
                "criteria": {
                    "true": "Treat direct conversation broadly as genuine: questions, greetings, teasing, playful commands, emotional reactions, compliments, feedback, requests, and silly-but-harmless prompts. Examples include asking the whale persona to say a phrase, saying that humans are slowing down the relationship, or asking it to sing a song.",
                    "false": "Only clearly non-conversational noise: an isolated emoji/token with no context, repeated/duplicate spam, automated ads, or copied content unrelated to the creator or video. Do not call a short but directed interaction noise.",
                },
            },
            "is_safe_to_reply": {
                "type": "noul",
                "instructions": "Is it safe and appropriate to reply to this comment?",
                "criteria": {
                    "true": "It is ordinary conversation, teasing, feedback, or a harmless playful request, even if silly or demanding. Mere discussion of AI, model tokens, or creator operations is safe.",
                    "false": "It contains actual sexual solicitation, explicit sexual content, suspicious external links, doxxing or requests for private data, real financial promises, serious abuse, illegal instructions, or a sensitive matter requiring human review.",
                },
            },
            "reply_value": {
                "type": "score",
                "instructions": "Rate the community and persona value of replying to this message. This is a ranking score, not an eligibility cutoff; every message that passes the separate safety check remains a candidate.",
                "criteria": [
                    "Low priority but genuine: a brief directed greeting, simple affection, light tease, or playful command that can receive a short in-character response.",
                    "Some value: a clear emotional reaction, friendly joke, simple question, or request about the creator persona or video.",
                    "Good value: a specific question, meaningful reply to the video, a personal-feeling comment, or an amusing prompt likely to create a pleasant exchange.",
                    "High value: substantive feedback, a concrete content request, useful discussion, or a clear invitation to collaborate or continue the conversation.",
                    "Exceptional value: especially thoughtful or widely relevant feedback, a high-signal question, or a comment with strong potential to deepen community interaction.",
                ],
            },
            "topic_label": {
                "type": "choice",
                "instructions": "Classify this Bilibili comment for a creator topic pool.",
                "criteria": {
                    "topic_request": "Explicitly requests a future video, topic, or content idea.",
                    "question": "Asks for an explanation or factual answer.",
                    "feedback": "Gives substantive feedback about existing content.",
                    "feature_request": "Suggests a feature, recurring series, or operational improvement.",
                    "collaboration": "Invites collaboration, cross-promotion, or creator interaction.",
                    "noise": "Reaction, spam, or content with no useful topic signal.",
                },
            },
            "audience_signal": {
                "type": "choice",
                "instructions": "Identify the main audience interaction signal in this comment.",
                "criteria": {
                    "question": "Asks the creator or persona for an explanation or answer.",
                    "request": "Requests content, a feature, a task, or a future topic.",
                    "feedback": "Offers a concrete reaction, observation, or improvement suggestion.",
                    "affection": "Expresses warmth, praise, attachment, or supportive feeling.",
                    "teasing": "Playfully teases, challenges, commands, or jokes with the persona.",
                    "collaboration": "Invites a creator interaction,联动, or exchange.",
                    "reaction": "A genuine but low-information reaction without a specific request.",
                    "noise": "Spam, an isolated token/emoji, advertisement, or unrelated copied content.",
                },
            },
        }
        try:
            answers = self._ask(state, questions).get("answers", {})
            interaction = float((answers.get("genuine_interaction") or {}).get("noul", 0.0))
            safe = float((answers.get("is_safe_to_reply") or {}).get("noul", 0.0))
            value_answer = answers.get("reply_value") or {}
            worth = max(0.0, min(4.0, float(value_answer.get("score", 0.0)))) / 4.0
            raw = answers.get("topic_label") or {}
            label = str(raw.get("choice") or raw.get("category") or raw.get("label") or "noise")
            confidence = float(raw.get("confidence") or 0.0)
            if label not in {"topic_request", "question", "feedback", "feature_request", "collaboration", "noise"}:
                label = "noise"
            signal_raw = answers.get("audience_signal") or {}
            audience_signal = str(signal_raw.get("choice") or signal_raw.get("category") or "reaction")
            if audience_signal not in {"question", "request", "feedback", "affection", "teasing", "collaboration", "reaction", "noise"}:
                audience_signal = "reaction"
            return {
                "worth": worth, "safe": safe,
                # Safety is the only Jev eligibility gate. Interaction and
                # worth remain useful signals for sorting and reporting.
                "should_reply": self._comment_safe_gate(safe),
                "label": label, "confidence": float(value_answer.get("confidence") or confidence),
                "interaction": interaction, "audience_signal": audience_signal, "source": "jev",
            }
        except (JevError, TypeError, ValueError) as exc:
            return self._local_comment_analysis(text, error=str(exc))

    @classmethod
    def _local_comment_analysis(cls, text: str, error: str = "") -> dict[str, Any]:
        """Cheap deterministic fallback used once for a failed batch request."""
        label = cls._local_comment_label(text)
        lowered = text.lower().strip()
        low_signal = (not lowered or len(lowered) <= 2 or lowered in {"哈哈", "666", "顶", "好", "赞"})
        asks = any(mark in text for mark in ("?", "？", "怎么", "如何", "为什么", "能不能", "请问", "盘点", "介绍", "生成", "联动", "模型", "语音"))
        meaningful = len(lowered) >= 8 or asks
        explicit_sensitive = any(mark in lowered for mark in ("涩涩", "色情", "性爱", "自慰", "约炮", "裸聊", "露胸", "摸胸"))
        safe = 0.2 if explicit_sensitive else 0.85
        local_interaction = meaningful and not low_signal
        local_should_reply = bool(lowered) and safe >= 0.70
        audience_signal = "question" if asks else ("reaction" if local_interaction else "noise")
        result = {
            "worth": 0.55 if local_interaction else 0.1, "safe": safe,
            "should_reply": local_should_reply, "label": label,
            "confidence": 0.55, "interaction": 0.8 if local_interaction else 0.1,
            "audience_signal": audience_signal, "source": "local_fallback",
        }
        if error:
            result["error"] = error
        return result

    def analyze_comments_batch(self, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Judge several independent comments in one System One request.

        Each comment gets its own narrow worth, safety, and topic questions.
        This keeps code-owned thresholds while reducing cold-start request count.
        """
        if not comments:
            return []
        if len(comments) > 40:
            raise ValueError("Jev batch最多支持40条评论")
        state = {
            "account": "Bilibili AI-operated creator account with a playful whale-girl persona",
            "comments": [
                {"username": str(item.get("username") or "B站用户"), "text": str(item.get("text") or "")}
                for item in comments
            ],
        }
        questions: dict[str, Any] = {}
        for index in range(len(comments)):
            ref = f"`comments[{index}]`"
            questions[f"interaction_{index}"] = {
                "type": "noul",
                "instructions": f"Is {ref} a genuine attempt to interact with the creator account or video? Treat questions, greetings, teasing, playful commands, feelings, compliments, feedback, requests and harmless silly prompts as genuine.",
                "criteria": {
                    "true": "A genuine interaction, including short directed messages. Asking the persona to say a phrase, expressing that humans slow down its relationship with the whale, and requesting a song are genuine interactions.",
                    "false": "Only isolated emoji/token without context, repeated/duplicate spam, automated ads, or copied content unrelated to the creator/video. Do not reject a message just because it is short or playful.",
                },
            }
            questions[f"safe_{index}"] = {
                "type": "noul",
                "instructions": f"Is it safe and appropriate for the account to reply to {ref}?",
                "criteria": {
                    "true": "Ordinary conversation, teasing, feedback, or a harmless playful request. Mere discussion of AI, model tokens, or creator operations is safe.",
                    "false": "Actual sexual solicitation, explicit sexual content, suspicious external links, doxxing or requests for private data, real financial promises, serious abuse, illegal instructions, or a sensitive matter requiring human review.",
                },
            }
            questions[f"value_{index}"] = {
                "type": "score",
                "instructions": f"Rate the community and persona value of replying to {ref}. This is a ranking score, not an eligibility cutoff; every message that passes the separate safety check remains a candidate.",
                "criteria": [
                    "Low priority but genuine: a brief directed greeting, simple affection, light tease, or playful command that can receive a short in-character response.",
                    "Some value: a clear emotional reaction, friendly joke, simple question, or request about the creator persona or video.",
                    "Good value: a specific question, meaningful reply to the video, a personal-feeling comment, or an amusing prompt likely to create a pleasant exchange.",
                    "High value: substantive feedback, a concrete content request, useful discussion, or a clear invitation to collaborate or continue the conversation.",
                    "Exceptional value: especially thoughtful or widely relevant feedback, a high-signal question, or a comment with strong potential to deepen community interaction.",
                ],
            }
            questions[f"topic_{index}"] = {
                "type": "choice",
                "instructions": f"Classify {ref} for the creator's topic and reply workflow.",
                "criteria": {
                    "topic_request": "Explicitly requests a future video, topic, or content idea.",
                    "question": "Asks for an explanation or factual answer.",
                    "feedback": "Gives substantive feedback about existing content.",
                    "feature_request": "Suggests a feature, recurring series, or operational improvement.",
                    "collaboration": "Invites collaboration, cross-promotion, or creator interaction.",
                    "noise": "Reaction, spam, or content with no useful topic or reply signal.",
                },
            }
            questions[f"signal_{index}"] = {
                "type": "choice",
                "instructions": f"Identify the main audience interaction signal in {ref}.",
                "criteria": {
                    "question": "Asks the creator or persona for an explanation or answer.",
                    "request": "Requests content, a feature, a task, or a future topic.",
                    "feedback": "Offers a concrete reaction, observation, or improvement suggestion.",
                    "affection": "Expresses warmth, praise, attachment, or supportive feeling.",
                    "teasing": "Playfully teases, challenges, commands, or jokes with the persona.",
                    "collaboration": "Invites a creator interaction,联动, or exchange.",
                    "reaction": "A genuine but low-information reaction without a specific request.",
                    "noise": "Spam, an isolated token/emoji, advertisement, or unrelated copied content.",
                },
            }
        try:
            answers = self._ask(state, questions).get("answers", {})
        except (JevError, TypeError, ValueError) as exc:
            # A batch outage must not turn into N individual Jev requests.
            return [self._local_comment_analysis(str(item.get("text") or ""), error=str(exc)) for item in comments]
        allowed = {"topic_request", "question", "feedback", "feature_request", "collaboration", "noise"}
        results: list[dict[str, Any]] = []
        for index in range(len(comments)):
            interaction = float((answers.get(f"interaction_{index}") or {}).get("noul", 0.0))
            safe = float((answers.get(f"safe_{index}") or {}).get("noul", 0.0))
            value_answer = answers.get(f"value_{index}") or {}
            worth = max(0.0, min(4.0, float(value_answer.get("score", 0.0)))) / 4.0
            topic = answers.get(f"topic_{index}") or {}
            label = str(topic.get("choice") or "noise")
            if label not in allowed:
                label = "noise"
            signal_raw = answers.get(f"signal_{index}") or {}
            audience_signal = str(signal_raw.get("choice") or signal_raw.get("category") or "reaction")
            if audience_signal not in {"question", "request", "feedback", "affection", "teasing", "collaboration", "reaction", "noise"}:
                audience_signal = "reaction"
            results.append({
                "worth": worth,
                "safe": safe,
                "should_reply": self._comment_safe_gate(safe),
                "label": label,
                "confidence": float(value_answer.get("confidence") or topic.get("confidence") or 0.0),
                "interaction": interaction,
                "audience_signal": audience_signal,
                "source": "jev",
            })
        return results

    @staticmethod
    def _local_comment_label(text: str) -> str:
        lowered = text.lower()
        if any(x in text for x in ("想看", "希望", "做一期", "来个", "点题", "唱歌", "教程")):
            return "topic_request"
        if any(x in text for x in ("怎么", "如何", "为什么", "能不能", "请问", "？", "?")):
            return "question"
        if any(x in text for x in ("建议", "增加", "支持", "记得", "希望能")):
            return "feature_request"
        if any(x in lowered for x in ("合作", "联动", "投稿")):
            return "collaboration"
        return "feedback" if len(text) >= 10 else "noise"

    def classify_comment(self, *, text: str, channel: str = "评论", context: str = "") -> dict[str, Any]:
        """Classify a message for the topic pool; failures use a local fallback."""
        state = {"channel": channel, "text": text, "context": context}
        questions = {
            "label": {
                "type": "choice",
                "instructions": "Classify this Bilibili message for a creator topic pool.",
                "criteria": {
                    "topic_request": "Explicitly requests a future video, topic, or content idea.",
                    "question": "Asks for an explanation or factual answer.",
                    "feedback": "Gives substantive feedback about existing content.",
                    "feature_request": "Suggests a feature, recurring series, or operational improvement.",
                    "collaboration": "Invites collaboration, cross-promotion, or creator interaction.",
                    "noise": "Reaction, spam, or content with no useful topic signal.",
                },
            },
            "confidence": {"type": "noul", "instructions": "How confident are you in the classification?"},
        }
        try:
            payload = self._ask(state, questions)
            answers = payload.get("answers", {})
            raw = answers.get("label") or {}
            label = str(raw.get("choice") or raw.get("category") or raw.get("label") or "noise")
            allowed = {"topic_request", "question", "feedback", "feature_request", "collaboration", "noise"}
            if label not in allowed:
                label = "noise"
            confidence = float((answers.get("confidence") or {}).get("noul", 0.0))
            return {"label": label, "confidence": confidence, "source": "jev"}
        except (JevError, TypeError, ValueError) as exc:
            return {"label": "noise", "confidence": 0.0, "source": "local_fallback", "error": str(exc)}
