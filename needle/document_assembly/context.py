from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


_NORMALISE_RE = re.compile(r"[^a-z0-9]+")


def normalize_field_name(name: str) -> str:
    return _NORMALISE_RE.sub("", str(name).strip().lower())


@dataclass
class AssemblyContext:
    values: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    confirmed: dict[str, bool] = field(default_factory=dict)
    choices: dict[str, Any] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.aliases = {
            str(key): ([str(item) for item in value] if isinstance(value, (list, tuple, set))
                       else [str(value)])
            for key, value in (self.aliases or {}).items()
        }
        self.values = dict(self.values or {})
        self.metadata = dict(self.metadata or {})
        self.confirmed = {str(key): bool(value) for key, value in (self.confirmed or {}).items()}
        self.choices = dict(self.choices or {})
        self.required_fields = [str(item) for item in (self.required_fields or [])]

    def alias_map(self) -> dict[str, str]:
        mapping = {}
        for key in self.values:
            mapping.setdefault(normalize_field_name(key), key)
        for key, aliases in self.aliases.items():
            mapping.setdefault(normalize_field_name(key), key)
            for alias in aliases:
                mapping.setdefault(normalize_field_name(alias), key)
        return mapping

    def resolve_name(self, name: str) -> str | None:
        return self.alias_map().get(normalize_field_name(name))

    def get(self, name: str, default: Any = None) -> Any:
        resolved = self.resolve_name(name)
        if resolved is None:
            return default
        if resolved in self.values:
            return self.values.get(resolved, default)
        needle = normalize_field_name(resolved)
        for key, value in self.values.items():
            if normalize_field_name(key) == needle:
                return value
        return default

    def has_value(self, name: str) -> bool:
        return self.get(name, None) is not None

    def is_confirmed(self, name: str) -> bool:
        resolved = self.resolve_name(name) or str(name)
        if resolved in self.confirmed:
            return self.confirmed[resolved]
        normalised = normalize_field_name(resolved)
        for key, value in self.confirmed.items():
            if normalize_field_name(key) == normalised:
                return value
        return False

    def merged(self, values: dict[str, Any] | None = None, *, metadata: dict[str, Any] | None = None,
               aliases: dict[str, list[str] | str] | None = None,
               confirmed: dict[str, bool] | None = None,
               choices: dict[str, Any] | None = None) -> "AssemblyContext":
        merged_aliases = {key: list(items) for key, items in self.aliases.items()}
        for key, items in (aliases or {}).items():
            merged_aliases[str(key)] = ([str(item) for item in items] if isinstance(items, (list, tuple, set))
                                        else [str(items)])
        merged_confirmed = dict(self.confirmed)
        merged_confirmed.update(confirmed or {})
        merged_choices = dict(self.choices)
        merged_choices.update(choices or {})
        merged_metadata = dict(self.metadata)
        merged_metadata.update(metadata or {})
        merged_values = dict(self.values)
        merged_values.update(values or {})
        return AssemblyContext(
            values=merged_values,
            aliases=merged_aliases,
            metadata=merged_metadata,
            confirmed=merged_confirmed,
            choices=merged_choices,
            required_fields=list(self.required_fields),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "aliases": self.aliases,
            "metadata": self.metadata,
            "confirmed": self.confirmed,
            "choices": self.choices,
            "required_fields": self.required_fields,
        }

    def to_json(self, **kwargs: Any) -> str:
        params = {"indent": 2, **kwargs}
        return json.dumps(self.to_dict(), **params)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssemblyContext":
        return cls(
            values=payload.get("values") or {},
            aliases=payload.get("aliases") or {},
            metadata=payload.get("metadata") or {},
            confirmed=payload.get("confirmed") or {},
            choices=payload.get("choices") or {},
            required_fields=payload.get("required_fields") or [],
        )

    @classmethod
    def from_json(cls, payload: str) -> "AssemblyContext":
        return cls.from_dict(json.loads(payload))
