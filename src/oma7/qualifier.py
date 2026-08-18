from __future__ import annotations

from .models import Observation, QualificationState, ResultStatus


def qualify_observation(observation: Observation) -> QualificationState:
    if observation.result == ResultStatus.UNKNOWN:
        return QualificationState.EXECUTION_FAILED
    if observation.result == ResultStatus.FAIL:
        return QualificationState.EXCLUDED_GOLD_REGRESSION
    if observation.result == ResultStatus.ERROR:
        return QualificationState.EXECUTION_FAILED
    return QualificationState.QUALIFIED

