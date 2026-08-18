from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import Observation, ResultStatus


def _normalize_status(value: Any) -> ResultStatus:
    try:
        return ResultStatus(value)
    except Exception:
        pass
    if value in ResultStatus.__members__:
        return ResultStatus[value]
    return ResultStatus.UNKNOWN


def normalize_b0_observation(payload: dict[str, Any]) -> Observation:
    subject = payload["subject_identity"]
    context = payload["verification_context_identity"]
    tests_status = {
        name: _normalize_status(status)
        for name, status in (payload.get("tests_status") or {}).items()
    }
    return Observation(
        subject_identity=subject,
        verification_context_identity=context,
        result=_normalize_status(payload.get("result")),
        tests_status=tests_status,
        raw={k: v for k, v in payload.items() if k not in {"subject_identity", "verification_context_identity", "tests_status", "result"}},
    )
