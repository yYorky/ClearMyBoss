from __future__ import annotations

import json
from pathlib import Path
from typing import Set


class DocumentCache:
    """Persistent set of document IDs stored in a JSON file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.ids: Set[str] = set()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            if isinstance(data, list):
                self.ids = set(str(x) for x in data)
        except FileNotFoundError:
            self.ids = set()
        except json.JSONDecodeError:
            self.ids = set()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self.ids)), encoding="utf-8")
