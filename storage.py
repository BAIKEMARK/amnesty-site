"""Small atomic JSON store used for cursors, memory and user state."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self, name: str, default: Any) -> Any:
        path = self.directory / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def save(self, name: str, value: Any) -> None:
        path = self.directory / name
        temp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(value, ensure_ascii=False, indent=2)
        # Windows 上杀软/索引器偶尔会短暂占用刚创建的 .tmp，重试几次比直接崩掉好。
        last_error: OSError | None = None
        for attempt in range(3):
            try:
                temp.write_text(text, encoding="utf-8")
                os.replace(temp, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        try:
            path.write_text(text, encoding="utf-8")
            return
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise last_error if last_error is not None else OSError(f"无法写入 {path}")
