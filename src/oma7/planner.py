from __future__ import annotations

from .preflight import RuntimePins, execution_context_identity_from_pins


def compute_execution_context_id(pins: RuntimePins) -> str:
    return execution_context_identity_from_pins(pins).identity()
