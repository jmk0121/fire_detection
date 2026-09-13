from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from app.schemas import PredictionResult, SensorSample


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

        self.model = tf.keras.models.load_model(self.model_path)
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
