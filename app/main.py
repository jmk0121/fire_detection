from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.research_api import router as research_router
from app.schemas import AnalyzeRequest, AnalysisResponse, HealthResponse
from app.services.analysis import FireAnalysisService
from app.services.briefing import GeminiBriefingService
from app.services.predictor import FirePredictor
from app.services.safety_rules import SafetyRuleEngine


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
LIVE_SNAPSHOT_PATH = APP_DIR.parent / "live_dashboard.json"


app = FastAPI(
    title="Fire Detection AI API",
    version="1.0.0",
    description=(
        "ESP32 센서 시계열과 선택한 CSV 건물정보로 피해등급을 예측하고 "
        "Gemini 현장 브리핑을 생성하는 교육용 API"
    ),
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(research_router)


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def get_analysis_service() -> FireAnalysisService:
    settings = get_settings()
    predictor = FirePredictor(
        data_path=settings.data_path,
        model_path=settings.model_path,
        preprocess_path=settings.preprocess_path,
    )
    briefing_service = GeminiBriefingService(settings)
    safety_rules = SafetyRuleEngine(
        settings.checklist_path,
        settings.low_confidence_threshold,
    )
    return FireAnalysisService(
        settings=settings,
        predictor=predictor,
        briefing_service=briefing_service,
        safety_rules=safety_rules,
    )


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/research", include_in_schema=False)
def research_dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "research.html")


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        model_file_exists=settings.model_path.exists(),
        preprocess_file_exists=settings.preprocess_path.exists(),
        data_file_exists=settings.data_path.exists(),
        gemini_configured=settings.llm_enabled and bool(settings.gemini_api_key),
        gemini_model=settings.gemini_model,
    )


@app.get("/api/v1/live", response_model=AnalysisResponse)
def live_snapshot() -> AnalysisResponse:
    if not LIVE_SNAPSHOT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="아직 ESP32 실시간 분석 데이터가 없습니다.",
        )

    try:
        return AnalysisResponse.model_validate_json(
            LIVE_SNAPSHOT_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="실시간 분석 데이터를 읽는 중입니다. 잠시 후 다시 시도하세요.",
        ) from error


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    try:
        return get_analysis_service().analyze(
            context_row=request.context_row,
            samples=request.samples,
            generate_briefing=request.generate_briefing,
        )
    except IndexError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
