from __future__ import annotations

from typing import Sequence

from app.schemas import SensorSample, SensorSummary


def summarize_sensor_window(
    samples: Sequence[SensorSample],
    sample_interval_seconds: float = 2.0,
) -> SensorSummary:
    if len(samples) < 2:
        raise ValueError("센서 요약에는 2개 이상의 샘플이 필요합니다.")

    first = samples[0]
    latest = samples[-1]

    return SensorSummary(
        sample_count=len(samples),
        window_seconds=(len(samples) - 1) * sample_interval_seconds,
        latest_temperature=latest.temperature,
        latest_humidity=latest.humidity,
        latest_gas1_ratio=latest.gas1_ratio,
        latest_gas2_ratio=latest.gas2_ratio,
        temperature_change=latest.temperature - first.temperature,
        gas1_ratio_change=latest.gas1_ratio - first.gas1_ratio,
        gas2_ratio_change=latest.gas2_ratio - first.gas2_ratio,
        max_temperature=max(sample.temperature for sample in samples),
        max_gas1_ratio=max(sample.gas1_ratio for sample in samples),
        max_gas2_ratio=max(sample.gas2_ratio for sample in samples),
    )
