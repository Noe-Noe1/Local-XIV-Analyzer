"""Conservative ActionEffect normalization and unknown collection."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedEffect:
    critical: bool | None
    direct_hit: bool | None
    absorbed: float | None
    source: str
    confidence: str


def _optional_bool(event, *keys):
    for key in keys:
        if key in event:
            value = event[key]
            if isinstance(value, bool):
                return value
            if value in (0, 1):
                return bool(value)
    return None


def _optional_amount(event, *keys):
    for key in keys:
        if key in event:
            try:
                return max(0.0, float(event[key]))
            except (TypeError, ValueError):
                return None
    return None


def decode_event(event):
    if not isinstance(event, dict):
        raise TypeError("event must be a dictionary")

    critical = _optional_bool(event, "critical", "isCritical")
    direct_hit = _optional_bool(event, "directHit", "isDirectHit")
    absorbed = _optional_amount(
        event,
        "absorbed",
        "shieldAbsorbed",
    )

    known = any(
        value is not None
        for value in (critical, direct_hit, absorbed)
    )

    return DecodedEffect(
        critical=critical,
        direct_hit=direct_hit,
        absorbed=absorbed,
        source="explicit_fields" if known else "unknown",
        confidence="high" if known else "unknown",
    )


def unknown_record(event, decoded=None):
    decoded = decoded or decode_event(event)
    if decoded.source != "unknown":
        return None

    return {
        "event_type": str(event.get("type") or ""),
        "ability_id": str(event.get("abilityGameID") or ""),
        "raw_effects": copy.deepcopy(event.get("rawEffects")),
        "reason": "no_supported_explicit_effect_fields",
    }


def serialize_unknown(record):
    return json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
