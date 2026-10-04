from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from app.schemas import PredictionResult, SensorSample


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextSnapshot:
    """One CSV row shared by the model input and the LLM input."""

    row_index: int
    model_frame: pd.DataFrame
    values: dict[str, Any]


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _remove_unsupported_keras_config(value: Any) -> None:
    """Make newer Keras config fields readable by the installed runtime."""
    if isinstance(value, dict):
        if value.get("class_name") == "GlorotUniform":
            config = value.get("config")
            if isinstance(config, dict):
                config.pop("input_axes", None)
                config.pop("output_axes", None)
        config = value.get("config")
        if isinstance(config, dict) and config.get("quantization_config") is None:
            config.pop("quantization_config", None)
        for child in value.values():
            _remove_unsupported_keras_config(child)
    elif isinstance(value, list):
        for child in value:
            _remove_unsupported_keras_config(child)


def _write_compatible_model_archive(source_path: Path, target_path: Path) -> None:
    with zipfile.ZipFile(source_path, "r") as source:
        config = json.loads(source.read("config.json"))
        _remove_unsupported_keras_config(config)

        with zipfile.ZipFile(target_path, "w") as target:
            for info in source.infolist():
                content = (
                    json.dumps(config, ensure_ascii=False).encode("utf-8")
                    if info.filename == "config.json"
                    else source.read(info.filename)
                )
                target.writestr(info, content)


def _load_keras_model(tf: Any, model_path: Path) -> Any:
    try:
        return tf.keras.models.load_model(model_path, compile=False)
    except TypeError as error:
        if "input_axes" not in str(error) and "output_axes" not in str(error):
            raise

        logger.warning(
            "저장된 Keras 모델의 initializer 축 설정을 현재 런타임에 맞게 "
            "임시 변환해 불러옵니다."
        )
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".keras",
            delete=False,
        )
        temporary_path = Path(temporary_file.name)
        temporary_file.close()
        try:
            _write_compatible_model_archive(model_path, temporary_path)
            return tf.keras.models.load_model(temporary_path, compile=False)
        finally:
            temporary_path.unlink(missing_ok=True)


class FirePredictor:
    def __init__(
        self,
        data_path: Path,
        model_path: Path,
        preprocess_path: Path,
    ) -> None:
        self.data_path = Path(data_path)
        self.model_path = Path(model_path)
        self.preprocess_path = Path(preprocess_path)

        bundle = joblib.load(self.preprocess_path)
        self.static_preprocessor = bundle["static_preprocessor"]
        self.sensor_scaler = bundle["sensor_scaler"]
        self.label_encoder = bundle["label_encoder"]
        self.static_features = list(bundle["static_features"])
        self.sequence_length = int(bundle["sequence_length"])
        self.sensor_channels = list(bundle["sensor_channels"])
        expected_channels = [
            "temperature",
            "humidity",
            "gas1_ratio",
            "gas2_ratio",
        ]
        if self.sensor_channels != expected_channels:
            raise ValueError(
                "현재 API 센서 스키마와 전처리기의 센서 채널 순서가 다릅니다: "
                f"{self.sensor_channels}"
            )

        # TensorFlow is imported lazily so non-model unit tests stay lightweight.
        import tensorflow as tf

        self.model = _load_keras_model(tf, self.model_path)
        self.context_data = pd.read_csv(self.data_path)

    def get_context(self, row_index: int) -> ContextSnapshot:
        if row_index < 0 or row_index >= len(self.context_data):
            raise IndexError(
                f"context_row는 0 ~ {len(self.context_data) - 1} 사이여야 합니다."
            )

        model_frame = self.context_data.iloc[[row_index]][
            self.static_features
        ].copy()
        values = {
            column: _json_value(model_frame.iloc[0][column])
            for column in self.static_features
        }
        return ContextSnapshot(
            row_index=row_index,
            model_frame=model_frame,
            values=values,
        )

    def predict(
        self,
        samples: Sequence[SensorSample],
        context: ContextSnapshot,
    ) -> PredictionResult:
        if len(samples) != self.sequence_length:
            raise ValueError(
                f"센서 샘플은 정확히 {self.sequence_length}개여야 합니다. "
                f"현재 {len(samples)}개입니다."
            )

        sequence = np.asarray(
            [
                [
                    sample.temperature,
                    sample.humidity,
                    sample.gas1_ratio,
                    sample.gas2_ratio,
                ]
                for sample in samples
            ],
            dtype=np.float32,
        )

        expected_shape = (self.sequence_length, len(self.sensor_channels))
        if sequence.shape != expected_shape:
            raise ValueError(
                f"센서 sequence shape 오류: {sequence.shape}, 필요: {expected_shape}"
            )

        static_input = self.static_preprocessor.transform(
            context.model_frame
        ).astype(np.float32)
        sequence_scaled = self.sensor_scaler.transform(sequence)
        sequence_scaled = sequence_scaled.reshape(
            1,
            self.sequence_length,
            len(self.sensor_channels),
        ).astype(np.float32)

        probabilities = self.model.predict(
            {
                "sensor_sequence": sequence_scaled,
                "static_input": static_input,
            },
            verbose=0,
        )[0]

        prediction_index = int(np.argmax(probabilities))
        grade = self.label_encoder.inverse_transform([prediction_index])[0]
        probability_map = {
            str(label): float(probability)
            for label, probability in zip(
                self.label_encoder.classes_, probabilities
            )
        }

        return PredictionResult(
            grade_code=str(grade),
            confidence=float(probabilities[prediction_index]),
            probabilities=probability_map,
        )
