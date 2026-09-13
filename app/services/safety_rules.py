from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas import OperationalGuidance, PredictionResult, SensorSummary


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class SafetyRuleEngine:
    def __init__(self, checklist_path: Path, low_confidence_threshold: float) -> None:
        with Path(checklist_path).open(encoding="utf-8") as file:
            source: dict[str, Any] = json.load(file)
        self.items = {
            rule_id: payload
            for rule_id, payload in source.items()
            if not rule_id.startswith("_")
        }
        self.low_confidence_threshold = low_confidence_threshold

    def select(
        self,
        static_context: dict[str, Any],
        prediction: PredictionResult,
        sensor_summary: SensorSummary,
    ) -> list[OperationalGuidance]:
        selected: list[tuple[str, str]] = [
            ("INITIAL_SIZE_UP", "모든 분석에서 적용"),
            ("COMMAND_TEAM_SAFETY", "모든 분석에서 적용"),
            ("ACCESS_WATER_POSITION", "모든 분석에서 적용"),
        ]

        basement_floors = _number(static_context.get("지하층수"))
        if basement_floors > 0:
            selected.append(
                ("BASEMENT_CONTROL", f"CSV 지하층수={basement_floors:g}")
            )

        above_floors = _number(static_context.get("지상층수"))
        if above_floors > 1:
            selected.append(
                ("MULTI_FLOOR_SPREAD", f"CSV 지상층수={above_floors:g}")
            )

        place_text = " ".join(
            str(static_context.get(name, ""))
            for name in ("장소대분류", "장소중분류", "장소소분류")
        )
        occupancy_keywords = (
            "공동주택",
            "병원",
            "요양",
            "숙박",
            "학교",
            "교육",
            "판매",
            "문화",
            "집회",
            "노유자",
        )
        multi_use = str(static_context.get("다중이용업소여부", "")).upper()
        if multi_use == "Y" or any(word in place_text for word in occupancy_keywords):
            selected.append(
                (
                    "OCCUPANCY_EVACUATION",
                    f"CSV 다중이용업소={multi_use or '미상'}, 장소={place_text.strip() or '미상'}",
                )
            )

        building_state = static_context.get("건물상태")
        structural_risk = _number(static_context.get("건물구조위험도"))
        if structural_risk > 0 or building_state not in (None, "", "사용중"):
            selected.append(
                (
                    "STRUCTURAL_HAZARD",
                    f"CSV 구조위험도={structural_risk:g}, 건물상태={building_state or '미상'}",
                )
            )

        rising_signals = []
        if sensor_summary.temperature_change > 0:
            rising_signals.append(
                f"온도 {sensor_summary.temperature_change:+.1f}℃"
            )
        if sensor_summary.gas1_ratio_change > 0:
            rising_signals.append(
                f"MQ1 {sensor_summary.gas1_ratio_change:+.2f}배"
            )
        if sensor_summary.gas2_ratio_change > 0:
            rising_signals.append(
                f"MQ2 {sensor_summary.gas2_ratio_change:+.2f}배"
            )
        if rising_signals:
            selected.append(
                ("RISING_SENSOR_SIGNAL", "구간 상승: " + ", ".join(rising_signals))
            )

        if prediction.confidence < self.low_confidence_threshold:
            selected.append(
                (
                    "LOW_CONFIDENCE",
                    "최고확률 "
                    f"{prediction.confidence * 100:.1f}% < 기준 "
                    f"{self.low_confidence_threshold * 100:.1f}%",
                )
            )

        guidance = [
            OperationalGuidance(id=rule_id, trigger=trigger, **self.items[rule_id])
            for rule_id, trigger in selected
        ]
        priority_order = {"즉시": 0, "우선": 1, "참고": 2}
        return sorted(guidance, key=lambda item: priority_order[item.priority])
