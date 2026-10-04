from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas import OperationalGuidance, PredictionResult, SensorSummary


# Project screening gates for the synthetic 30-second sensor window. These are
# not physical backdraft/flashover thresholds and never produce a probability.
RAPID_TEMPERATURE_RISE_C = 8.0
ELEVATED_SENSOR_TEMPERATURE_C = 40.0
COMBUSTION_SIGNAL_RISE = 0.5


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _count(value: Any) -> str:
    number = _number(value)
    return f"{number:g}"


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
        selected: list[tuple[str, str]] = []
        basement_floors = _number(static_context.get("지하층수"))
        above_floors = _number(static_context.get("지상층수"))
        place_parts = [
            _text(static_context.get(name))
            for name in ("장소대분류", "장소중분류", "장소소분류")
        ]
        place_parts = [part for part in place_parts if part]
        place_text = "·".join(place_parts)
        place_short = (
            _text(static_context.get("장소중분류"))
            or _text(static_context.get("장소대분류"))
            or "대상 건물"
        )
        rapid_temperature_rise = (
            sensor_summary.temperature_change >= RAPID_TEMPERATURE_RISE_C
        )
        elevated_temperature = (
            sensor_summary.max_temperature >= ELEVATED_SENSOR_TEMPERATURE_C
        )
        combustion_signal_rise = (
            sensor_summary.gas1_ratio_change >= COMBUSTION_SIGNAL_RISE
            or sensor_summary.gas2_ratio_change >= COMBUSTION_SIGNAL_RISE
        )
        rapid_fire_change = (
            rapid_temperature_rise
            and elevated_temperature
            and combustion_signal_rise
        )

        evidence = (
            f"30초 온도 {sensor_summary.temperature_change:+.1f}℃, "
            f"가스1 {sensor_summary.gas1_ratio_change:+.2f}배, "
            f"가스2 {sensor_summary.gas2_ratio_change:+.2f}배"
        )
        if rapid_fire_change and basement_floors > 0:
            selected.append(
                (
                    "BACKDRAFT_INDICATOR_CHECK",
                    f"{evidence} · 지하 {_count(basement_floors)}층",
                )
            )
        if rapid_fire_change:
            selected.append(("FLASHOVER_INDICATOR_CHECK", evidence))

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
        multi_use = _text(static_context.get("다중이용업소여부")).upper()
        if multi_use == "Y" or any(word in place_text for word in occupancy_keywords):
            selected.append(
                (
                    "OCCUPANCY_EVACUATION",
                    f"등록용도 {place_text or '미상'}",
                )
            )

        if basement_floors > 0:
            selected.append(
                ("BASEMENT_CONTROL", f"지하 {_count(basement_floors)}층")
            )

        if above_floors > 1:
            selected.append(
                ("MULTI_FLOOR_SPREAD", f"지상 {_count(above_floors)}층")
            )

        selected.extend(
            [
                ("INITIAL_SIZE_UP", "현장 기본 확인"),
                ("COMMAND_TEAM_SAFETY", "진입 전 기본 확인"),
                ("ACCESS_WATER_POSITION", "현장 기본 확인"),
            ]
        )

        building_state = static_context.get("건물상태")
        structural_risk = _number(static_context.get("건물구조위험도"))
        if structural_risk > 0 or building_state not in (None, "", "사용중"):
            selected.append(
                (
                    "STRUCTURAL_HAZARD",
                    f"건물상태 {building_state or '미상'} · 구조위험도 {structural_risk:g}",
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
                ("RISING_SENSOR_SIGNAL", "30초 변화 · " + ", ".join(rising_signals))
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

        guidance: list[OperationalGuidance] = []
        for rule_id, trigger in selected:
            payload = dict(self.items[rule_id])
            if rule_id == "BACKDRAFT_INDICATOR_CHECK" and basement_floors > 0:
                payload["action"] = (
                    f"지하 {_count(basement_floors)}층 출입구를 포함한 개구부 정면을 "
                    "피하고 문·창 개방과 진입을 보류한 채, 검댕 낀 창·유리 균열·"
                    "맥동성 짙은 연기·화염 부재를 외부에서 확인해 즉시 보고합니다."
                )
            elif rule_id == "FLASHOVER_INDICATOR_CHECK":
                payload["action"] = (
                    f"{place_short} 내부의 열기 급증·상층부 화염·가연물 발연·방수 직후 "
                    "증기화를 확인하고, 징후가 있으면 즉시 전파한 뒤 퇴로와 호스라인을 "
                    "확보해 진입 지속 여부를 재평가합니다."
                )
            elif rule_id == "OCCUPANCY_EVACUATION":
                payload["title"] = f"{place_short} 재실자·대피 확인"
                payload["action"] = (
                    f"{place_text or place_short} 건물이므로 관계인에게 구역별 재실 인원, "
                    "마지막 확인 위치와 대피 완료 여부를 확인하고 화재층·상층"
                    + ("·지하층" if basement_floors > 0 else "")
                    + " 수색 우선순위를 지휘관에게 보고합니다."
                )
            elif rule_id == "BASEMENT_CONTROL":
                payload["action"] = (
                    f"지하 {_count(basement_floors)}층의 출입구·계단·대체 퇴로를 먼저 "
                    "확인하고 계단 상부 예비 호스와 출입구 안전관찰 대원을 배치해 "
                    "진입 인원과 퇴로를 관리합니다."
                )
            elif rule_id == "MULTI_FLOOR_SPREAD":
                payload["action"] = (
                    f"지상 {_count(above_floors)}층 {place_short}이므로 실제 화재층을 "
                    "기준으로 상층 구역·피난계단·방화문 상태를 확인하고 수색·"
                    "연소확대 정보를 지휘관에게 보고합니다."
                )
            guidance.append(
                OperationalGuidance(id=rule_id, trigger=trigger, **payload)
            )
        priority_order = {"즉시": 0, "우선": 1, "참고": 2}
        return sorted(guidance, key=lambda item: priority_order[item.priority])
