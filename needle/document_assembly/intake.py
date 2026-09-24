from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any

from .context import AssemblyContext


@dataclass
class IntakeExtractionResult:
    context: AssemblyContext
    extracted_values: dict[str, Any]
    applied_values: dict[str, Any]
    preserved_confirmed_fields: list[str] = field(default_factory=list)
    conflicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "extracted_values": self.extracted_values,
            "applied_values": self.applied_values,
            "preserved_confirmed_fields": self.preserved_confirmed_fields,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
        }


def extract_context_from_intake(extractor: Any, intake: str, schema: type | dict, *,
                                existing_context: AssemblyContext | None = None,
                                allow_overwrite_confirmed: bool = False,
                                strict: bool = True,
                                system: str | None = None,
                                max_new_tokens: int = 512) -> IntakeExtractionResult:
    current = existing_context or AssemblyContext()
    raw = _call_extractor(extractor, intake, schema, strict=strict,
                          system=system, max_new_tokens=max_new_tokens)
    extracted = _to_mapping(raw)
    applied = {}
    preserved = []
    conflicts = {}
    merged = dict(current.values)
    for key, value in extracted.items():
        if value is None:
            continue
        canonical = current.resolve_name(key) or str(key)
        existing = current.get(canonical)
        if (current.is_confirmed(canonical) and existing is not None and existing != value
                and not allow_overwrite_confirmed):
            preserved.append(canonical)
            conflicts[canonical] = {"existing": existing, "proposed": value}
            continue
        merged[canonical] = value
        applied[canonical] = value
    confirmed = dict(current.confirmed)
    for key in applied:
        confirmed.setdefault(key, False)
    context = current.merged(merged, confirmed=confirmed)
    warnings = []
    if preserved:
        warnings.append("confirmed values were preserved and should be reviewed before applying updates")
    return IntakeExtractionResult(
        context=context,
        extracted_values=extracted,
        applied_values=applied,
        preserved_confirmed_fields=preserved,
        conflicts=conflicts,
        warnings=warnings,
    )


def _call_extractor(extractor: Any, intake: str, schema: type | dict, **kwargs: Any) -> Any:
    target = getattr(extractor, "extract", extractor)
    signature = inspect.signature(target)
    supported = {
        key: value for key, value in kwargs.items()
        if key in signature.parameters
    }
    return target(intake, schema, **supported)


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    raise TypeError("extractor returned an unsupported result type")
