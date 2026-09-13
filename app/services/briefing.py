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
        building_type = self._display(static_context.get("건축형태"))
        roof = self._display(static_context.get("지붕구조"))
        state = self._display(static_context.get("건물상태"))
        place_parts = [
            self._display(static_context.get("장소대분류"), ""),
            self._display(static_context.get("장소중분류"), ""),
            self._display(static_context.get("장소소분류"), ""),
        ]
        place = " > ".join(part for part in place_parts if part) or "확인되지 않음"
        above_floors = self._display_count(static_context.get("지상층수"))
        below_floors = self._display_count(static_context.get("지하층수"))
        fire_target = self._display(static_context.get("특정소방대상물"))
        fire_management = self._display(static_context.get("방화관리대상여부"))
        multi_use = self._display(static_context.get("다중이용업소여부"))
        probabilities = ", ".join(
            f"등급 {grade} {probability * 100:.1f}%"
            for grade, probability in sorted(prediction.probabilities.items())
        )
        immediate_items = [
            item for item in operational_guidance if item.priority == "즉시"
        ][:3]
        priority_text = " ".join(
            f"{index}. {item.title}: {item.action}"
            for index, item in enumerate(immediate_items, start=1)
        )
        if not priority_text:
            priority_text = "승인된 현장 확인 항목이 없습니다."

        return SafetyBriefing(
            headline=(
                f"모델은 피해등급 {prediction.grade_code}를 가장 높게 예측했습니다 "
                f"({prediction.confidence * 100:.1f}%). 현장 관측으로 즉시 재평가하십시오."
            ),
            situation_summary=(
                f"[센서 관측] 최근 {sensor_summary.window_seconds:.0f}초 동안 온도는 "
                f"{sensor_summary.temperature_change:+.1f}℃ 변해 현재 "
                f"{sensor_summary.latest_temperature:.1f}℃, 습도는 "
                f"{sensor_summary.latest_humidity:.1f}%입니다. "
                f"MQ1 비율은 {sensor_summary.latest_gas1_ratio:.2f}배"
                f"(구간 처음보다 {sensor_summary.gas1_ratio_change:+.2f}), "
                f"MQ2 비율은 "
                f"{sensor_summary.latest_gas2_ratio:.2f}배"
                f"(구간 처음보다 {sensor_summary.gas2_ratio_change:+.2f})입니다. "
                f"[모델 추론] 등급별 출력은 {probabilities}입니다. "
                "센서 위치 밖의 화재층·연기 방향·요구조자·붕괴위험은 이 값으로 알 수 없습니다."
            ),
            context_summary=(
                f"[등록정보] LSTM에 함께 입력된 건물 맥락은 {building_type}, {structure}, "
                f"지붕 {roof}, 지상 {above_floors}층·지하 {below_floors}층, "
                f"장소 {place}, 건물상태 {state}입니다. 등록 정보상 "
                f"특정소방대상물은 {fire_target}, 방화관리대상여부는 "
                f"{fire_management}, 다중이용업소여부는 {multi_use}입니다."
            ),
            operational_summary=(
                "[현장지휘 우선순위] 모델이 새 전술을 결정한 것이 아니라, 입력 조건에 "
                f"맞춰 소방청 절차에서 우선 표시한 항목입니다. {priority_text}"
            ),
            uncertainty=(
                "합성 데이터로 학습한 교육용 모델이며 피해등급은 화세, 진입 가능성, "
                "붕괴 또는 인명위험을 직접 판정하지 않습니다. 실제 소방 활동은 "
                "현장지휘관의 상황평가·명령과 소속기관 절차를 따릅니다."
            ),
            operational_guidance=operational_guidance,
            source=source,
            model=None,
            generation_note=reason,
        )
