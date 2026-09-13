from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_path: Path
    model_path: Path
    preprocess_path: Path
    checklist_path: Path
    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_seconds: float
    llm_enabled: bool
    llm_min_interval_seconds: float
    low_confidence_threshold: float
    sensor_sample_interval_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_path=BASE_DIR / os.getenv(
                "FIRE_DATA_PATH", "fire_training_synthetic(1).csv"
            ),
            model_path=BASE_DIR / os.getenv("FIRE_MODEL_PATH", "fire_lstm.keras"),
            preprocess_path=BASE_DIR
            / os.getenv("FIRE_PREPROCESS_PATH", "lstm_preprocessing.joblib"),
            checklist_path=BASE_DIR
            / os.getenv("FIRE_CHECKLIST_PATH", "data/approved_checklists.json"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_timeout_seconds=float(
                os.getenv("GEMINI_TIMEOUT_SECONDS", "8")
            ),
            llm_enabled=_env_bool("LLM_ENABLED", True),
            llm_min_interval_seconds=float(
                os.getenv("LLM_MIN_INTERVAL_SECONDS", "30")
            ),
            low_confidence_threshold=float(
                os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.65")
            ),
            sensor_sample_interval_seconds=float(
                os.getenv("SENSOR_SAMPLE_INTERVAL_SECONDS", "2")
            ),
        )
