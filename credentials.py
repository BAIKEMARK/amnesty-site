"""Credential environment-variable helpers.

This module contains names and precedence only.  It never persists, logs, or
validates secret values.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import TypeVar


T = TypeVar("T")


def environment_value(
    canonical: str,
    aliases: Iterable[str] = (),
    *,
    default: T = None,  # type: ignore[assignment]
    environ: Mapping[str, str] | None = None,
) -> str | T:
    """Return the first explicitly defined variable.

    The canonical name always wins, followed by aliases in declaration order.
    Presence is checked instead of truthiness so an explicitly empty variable
    can still disable a value stored in a local compatibility file.
    """

    source = os.environ if environ is None else environ
    for name in (canonical, *aliases):
        if name in source:
            return source[name]
    return default


# Canonical names are stable public configuration.  The aliases below remain
# supported for existing machines and CI jobs.
LLM_API_KEY_ENV = "BILI_AGENT_LLM_API_KEY"
LLM_API_KEY_ALIASES = ("BILI_AGENT_API_KEY",)
EMBEDDING_API_KEY_ENV = "BILI_AGENT_EMBEDDING_API_KEY"
QQ_APP_ID_ENV = "BILI_AGENT_QQ_APP_ID"
QQ_APP_ID_ALIASES = ("QQBOT_APP_ID",)
QQ_APP_SECRET_ENV = "BILI_AGENT_QQ_APP_SECRET"
QQ_APP_SECRET_ALIASES = ("QQBOT_APP_SECRET",)
STEP_API_KEY_ENV = "BILI_AGENT_STEP_KEY"
STEP_API_KEY_ALIASES = ("STEP_KEY",)
