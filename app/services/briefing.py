from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from app.config import Settings
from app.schemas import (
    GeneratedBriefingContent,
    OperationalGuidance,
    PredictionResult,
    SafetyBriefing,
    SensorSummary,
)


logger = logging.getLogger(__name__)


class GeminiBriefingService:
    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.model = settings.gemini_model
        self.prompt = (
            Path(__file__).resolve().parent.parent
            / "prompts"
            / "fire_briefing_v1.txt"
        ).read_text(encoding="utf-8")
        self.client = client

        if self.client is None and self.is_configured:
            try:
                from google import genai
                from google.genai import types
            except ImportError as error:
                raise RuntimeError(
                    "google-genai가 설치되지 않았습니다. "
                    "pip install -r requirements_lstm.txt를 실행하세요."
                ) from error

            self.client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=int(settings.gemini_timeout_seconds * 1000)
                ),
            )

    @property
    def is_configured(self) -> bool:
        return self.settings.llm_enabled and bool(self.settings.gemini_api_key)

    def generate(
        self,
        prediction: PredictionResult,
        sensor_summary: SensorSummary,
        static_context: dict[str, Any],
        operational_guidance: list[OperationalGuidance],
    ) -> SafetyBriefing:
        if not self.settings.llm_enabled:
            return self._demo(
                prediction,
                sensor_summary,
                static_context,
                operational_guidance,
                "demo",
                "LLM_ENABLED가 false입니다.",
            )
        if not self.settings.gemini_api_key or self.client is None:
            return self._demo(
                prediction,
                sensor_summary,
                static_context,
                operational_guidance,
                "demo",
                "GEMINI_API_KEY가 설정되지 않아 데모 설명문을 생성했습니다.",
            )

        fact_packet = {
            "prediction": prediction.model_dump(),
            "sensor_summary": sensor_summary.model_dump(),
            # This is the exact normalized row used for static model preprocessing.
            "static_context_used_by_lstm": static_context,
            # Gemini may summarize these reviewed items, but may not invent tactics.
            "approved_operational_guidance": [
                item.model_dump() for item in operational_guidance
            ],
        }
        model_input = (
            "분석 입력 JSON:\n"
            + json.dumps(fact_packet, ensure_ascii=False, separators=(",", ":"))
        )

        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=model_input,
                system_instruction=self.prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": GeneratedBriefingContent.model_json_schema(),
                },
                store=False,
            )
            content = GeneratedBriefingContent.model_validate_json(
                interaction.output_text
            )
            return SafetyBriefing(
                **content.model_dump(),
                operational_guidance=operational_guidance,
                source="gemini",
                model=self.model,
            )
        except Exception as error:
            logger.exception("Gemini 브리핑 생성에 실패했습니다.")
            return self._demo(
                prediction,
                sensor_summary,
                static_context,
                operational_guidance,
                "fallback",
                f"Gemini 호출 실패 ({type(error).__name__})",
            )

    @staticmethod
    def _display(value: Any, default: str = "확인되지 않음") -> str:
        if value is None or str(value).strip() == "":
            return default
        return str(value)

    @staticmethod
    def _display_count(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "확인되지 않음"
        return str(int(number)) if number.is_integer() else str(number)

    def _demo(
        self,
        prediction: PredictionResult,
        sensor_summary: SensorSummary,
        static_context: dict[str, Any],
        operational_guidance: list[OperationalGuidance],
        source: Literal["demo", "fallback"],
        reason: str,
    ) -> SafetyBriefing:
        structure = self._display(static_context.get("건물구조"))
        place_parts = [
            self._display(static_context.get("장소대분류"), ""),
            self._display(static_context.get("장소중분류"), ""),
            self._display(static_context.get("장소소분류"), ""),
        ]
        place = "·".join(part for part in place_parts if part) or "확인되지 않음"
        above_floors = self._display_count(static_context.get("지상층수"))
        below_floors = self._display_count(static_context.get("지하층수"))
        immediate_items = [
            item for item in operational_guidance if item.priority == "즉시"
        ][:3]
        primary_action = (
            immediate_items[0].title if immediate_items else "현장 상황평가"
        )
        priority_text = " ".join(
            f"{index}. {item.title}: {item.action}"
            for index, item in enumerate(immediate_items, start=1)
        )
        if not priority_text:
            priority_text = "승인된 현장 확인 항목이 없습니다."

        return SafetyBriefing(
            headline=(
                f"피해등급 {prediction.grade_code} · 신뢰도 "
                f"{prediction.confidence * 100:.1f}% · 우선: {primary_action}"
            ),
            situation_summary=(
                f"30초: 온도 {sensor_summary.latest_temperature:.1f}℃"
                f"({sensor_summary.temperature_change:+.1f}℃) · 가스1 "
                f"{sensor_summary.gas1_ratio_change:+.2f}배 · 가스2 "
                f"{sensor_summary.gas2_ratio_change:+.2f}배. "
                f"{place}·지상 {above_floors}/지하 {below_floors}층 · 피해등급 "
                f"{prediction.grade_code}({prediction.confidence * 100:.1f}%) · "
                f"우선: {primary_action}."
            ),
            context_summary=(
                f"{structure} · 지상 {above_floors}층/지하 {below_floors}층 · {place}"
            ),
            operational_summary=priority_text,
            uncertainty="교육용 결과 · 현장지휘관 판단과 소속기관 절차 우선.",
            operational_guidance=operational_guidance,
            source=source,
            model=None,
            generation_note=reason,
        )
