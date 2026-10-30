from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_UI_CONFIG_PATH = Path(__file__).with_name("ui_config.json")


def _string_map(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    cleaned = {}
    for key, label in value.items():
        if not isinstance(key, str) or not isinstance(label, str):
            continue
        key = key.strip()
        label = label.strip()
        if key and label:
            cleaned[key] = label
    return cleaned


@dataclass(frozen=True)
class UiConfig:
    device_aliases: dict[str, str] = field(default_factory=dict)
    matrix_aliases: dict[str, str] = field(default_factory=dict)

    def device_label(self, name: str) -> str:
        label = name
        for source, target in self.device_aliases.items():
            label = re.sub(
                re.escape(source),
                lambda match: target,
                label,
                flags=re.IGNORECASE,
            )
        return label

    def matrix_label(self, label: str) -> str:
        aliases = {
            key.casefold(): value
            for key, value in self.matrix_aliases.items()
        }
        return aliases.get(label.casefold(), label)


def load_ui_config(path: Path | str | None = None) -> UiConfig:
    config_path = (
        Path(path)
        if path is not None
        else DEFAULT_UI_CONFIG_PATH
    )

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return UiConfig()

    if not isinstance(data, dict):
        return UiConfig()

    return UiConfig(
        device_aliases=_string_map(data.get("device_aliases")),
        matrix_aliases=_string_map(data.get("matrix_aliases")),
    )
