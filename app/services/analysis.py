from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.schemas import AnalysisResponse, SensorSample
from app.services.briefing import GeminiBriefingService
from app.services.predictor import FirePredictor
from app.services.safety_rules import SafetyRuleEngine
from app.services.sensor_summary import summarize_sensor_window


class FireAnalysisService:
    def __init__(
        self,
        settings: Settings,
        predictor: FirePredictor,
        briefing_service: GeminiBriefingService,
        safety_rules: SafetyRuleEngine,
    ) -> None:
        self.settings = settings
        self.predictor = predictor
        self.briefing_service = briefing_service
        self.safety_rules = safety_rules

    def analyze(
        self,
        context_row: int,
        samples: list[SensorSample],
        generate_briefing: bool = True,
    ) -> AnalysisResponse:
        context = self.predictor.get_context(context_row)
        prediction = self.predictor.predict(samples, context)
        summary = summarize_sensor_window(
            samples,
            self.settings.sensor_sample_interval_seconds,
        )
        operational_guidance = self.safety_rules.select(
            context.values,
            prediction,
            summary,
        )
        briefing = None
        if generate_briefing:
            briefing = self.briefing_service.generate(
                prediction=prediction,
                sensor_summary=summary,
                static_context=context.values,
                operational_guidance=operational_guidance,
            )

        return AnalysisResponse(
            generated_at=datetime.now().astimezone(),
            context_row=context.row_index,
            static_context=context.values,
            sensor_summary=summary,
            prediction=prediction,
            briefing=briefing,
        )
