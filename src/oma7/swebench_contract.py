from __future__ import annotations


def effective_model_patch(prediction: dict, skip_patch: bool) -> str:
    if skip_patch:
        return ""
    return str(prediction.get("model_patch", ""))

