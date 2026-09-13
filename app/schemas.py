from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SensorSample(BaseModel):
    temperature: float = Field(ge=-100, le=300)
    humidity: float = Field(ge=0, le=100)
    gas1_ratio: float = Field(ge=0)
    gas2_ratio: float = Field(ge=0)


class AnalyzeRequest(BaseModel):
    context_row: int = Field(default=0, ge=0)
    samples: list[SensorSample] = Field(min_length=16, max_length=16)
    generate_briefing: bool = True


class PredictionResult(BaseModel):
    grade_code: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class SensorSummary(BaseModel):
    sample_count: int
    window_seconds: float
    latest_temperature: float
    latest_humidity: float
    latest_gas1_ratio: float
    latest_gas2_ratio: float
    temperature_change: float
    gas1_ratio_change: float
    gas2_ratio_change: float
    max_temperature: float
    max_gas1_ratio: float
    max_gas2_ratio: float


class OperationalGuidance(BaseModel):
    id: str
    priority: Literal["즉시", "우선", "참고"]
    category: str
    title: str
    action: str
    rationale: str
    basis: str
    trigger: str


class GeneratedBriefingContent(BaseModel):
    headline: str = Field(min_length=1, max_length=160)
    situation_summary: str = Field(min_length=1, max_length=700)
    context_summary: str = Field(min_length=1, max_length=500)
    operational_summary: str = Field(min_length=1, max_length=700)
    uncertainty: str = Field(min_length=1, max_length=400)

    @field_validator(
        "headline",
        "situation_summary",
        "context_summary",
        "operational_summary",
        "uncertainty",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class SafetyBriefing(GeneratedBriefingContent):
    operational_guidance: list[OperationalGuidance]
    source: Literal["gemini", "demo", "fallback"]
    model: str | None = None
    generation_note: str | None = None


class AnalysisResponse(BaseModel):
    generated_at: datetime
    context_row: int
    static_context: dict[str, Any]
    sensor_summary: SensorSummary
    prediction: PredictionResult
    briefing: SafetyBriefing | None
    prototype_notice: str = (
        "합성 데이터 기반 교육용 프로토타입이며 실제 현장 지휘 판단을 대체하지 않습니다."
    )


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: Literal["ok"] = "ok"
    model_file_exists: bool
    preprocess_file_exists: bool
    data_file_exists: bool
    gemini_configured: bool
    gemini_model: str
