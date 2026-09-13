from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from app.config import BASE_DIR, Settings
from app.schemas import OperationalGuidance, PredictionResult, SensorSample
from app.services.analysis import FireAnalysisService
from app.services.briefing import GeminiBriefingService
from app.services.safety_rules import SafetyRuleEngine
from app.services.sensor_summary import summarize_sensor_window


def make_settings(api_key: str | None) -> Settings:
    return Settings(
        data_path=BASE_DIR / "fire_training_synthetic(1).csv",
        model_path=BASE_DIR / "fire_lstm.keras",
        preprocess_path=BASE_DIR / "lstm_preprocessing.joblib",
        checklist_path=BASE_DIR / "data" / "approved_checklists.json",
        gemini_api_key=api_key,
        gemini_model="gemini-test-model",
        gemini_timeout_seconds=1,
        llm_enabled=True,
        llm_min_interval_seconds=30,
        low_confidence_threshold=0.65,
        sensor_sample_interval_seconds=2,
    )


def sample_window() -> list[SensorSample]:
    return [
        SensorSample(
            temperature=20 + index,
            humidity=50 - index,
            gas1_ratio=1 + index / 10,
            gas2_ratio=1 + index / 20,
        )
        for index in range(16)
    ]


class FakeInteractions:
    def __init__(self) -> None:
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs
        output = {
            "headline": "피해등급 1이 가장 높은 확률로 예측되었습니다.",
            "situation_summary": "최근 센서 구간에서 온도와 가스 비율이 변했습니다.",
            "context_summary": "선택된 철근콘크리트조 공동주택 정보를 함께 확인했습니다.",
            "operational_summary": "즉시 초기 상황평가와 지하층 퇴로를 확인합니다.",
            "uncertainty": "교육용 보조 결과이며 현장 판단을 대체하지 않습니다.",
        }
        return SimpleNamespace(output_text=json.dumps(output, ensure_ascii=False))


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()


class FakePredictor:
    def __init__(self, context: dict, prediction: PredictionResult) -> None:
        self.snapshot = SimpleNamespace(
            row_index=7,
            values=context,
            model_frame=object(),
        )
        self.prediction = prediction
        self.received_context = None

    def get_context(self, row_index: int):
        if row_index != 7:
            raise IndexError(row_index)
        return self.snapshot

    def predict(self, samples, context):
        self.received_context = context
        return self.prediction


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prediction = PredictionResult(
            grade_code="1",
            confidence=0.72,
            probabilities={"0": 0.2, "1": 0.72, "2": 0.08},
        )
        self.summary = summarize_sensor_window(sample_window(), 2)
        self.context = {
            "건물구조": "철근콘크리트조",
            "장소중분류": "공동주택",
            "지하층수": 1.0,
            "다중이용업소여부": "N",
            "건물상태": "사용중",
        }
        self.guidance = [
            OperationalGuidance(
                id="TEST_GUIDANCE",
                priority="즉시",
                category="상황평가",
                title="승인된 현장 확인",
                action="승인된 확인 문구",
                rationale="센서만으로 확인할 수 없는 정보입니다.",
                basis="테스트 절차",
                trigger="테스트 조건",
            )
        ]

    def test_sensor_summary_uses_full_window(self) -> None:
        self.assertEqual(self.summary.sample_count, 16)
        self.assertEqual(self.summary.window_seconds, 30)
        self.assertAlmostEqual(self.summary.temperature_change, 15)
        self.assertAlmostEqual(self.summary.gas1_ratio_change, 1.5)

    def test_rule_engine_uses_context_and_probability(self) -> None:
        engine = SafetyRuleEngine(
            BASE_DIR / "data" / "approved_checklists.json",
            low_confidence_threshold=0.8,
        )
        guidance = engine.select(self.context, self.prediction, self.summary)
        self.assertTrue(any("지하층" in item.title for item in guidance))
        self.assertTrue(any(item.id == "LOW_CONFIDENCE" for item in guidance))
        self.assertTrue(any(item.basis.startswith("소방청") for item in guidance))

    def test_gemini_receives_exact_static_context(self) -> None:
        client = FakeClient()
        service = GeminiBriefingService(make_settings("test-key"), client=client)
        result = service.generate(
            self.prediction,
            self.summary,
            self.context,
            self.guidance,
        )

        self.assertEqual(result.source, "gemini")
        request_text = client.interactions.last_request["input"]
        fact_json = request_text.split("분석 입력 JSON:\n", maxsplit=1)[1]
        facts = json.loads(fact_json)
        self.assertEqual(facts["static_context_used_by_lstm"], self.context)
        self.assertEqual(result.operational_guidance, self.guidance)
        self.assertEqual(
            facts["approved_operational_guidance"][0]["id"],
            "TEST_GUIDANCE",
        )
        self.assertIn("입력 JSON의 사실만", client.interactions.last_request["system_instruction"])
        self.assertIn("없는 진입, 방수", client.interactions.last_request["system_instruction"])
        self.assertFalse(client.interactions.last_request["store"])

    def test_missing_key_returns_realistic_demo(self) -> None:
        service = GeminiBriefingService(make_settings(None))
        result = service.generate(
            self.prediction,
            self.summary,
            self.context,
            self.guidance,
        )
        self.assertEqual(result.source, "demo")
        self.assertIn("GEMINI_API_KEY", result.generation_note)
        self.assertEqual(result.operational_guidance, self.guidance)
        self.assertIn("등급별 출력", result.situation_summary)
        self.assertIn("철근콘크리트조", result.context_summary)
        self.assertIn("승인된 현장 확인", result.operational_summary)

    def test_analysis_reuses_one_context_snapshot(self) -> None:
        settings = make_settings(None)
        predictor = FakePredictor(self.context, self.prediction)
        analysis = FireAnalysisService(
            settings=settings,
            predictor=predictor,
            briefing_service=GeminiBriefingService(settings),
            safety_rules=SafetyRuleEngine(
                settings.checklist_path,
                settings.low_confidence_threshold,
            ),
        )

        result = analysis.analyze(7, sample_window())

        self.assertIs(predictor.received_context, predictor.snapshot)
        self.assertEqual(result.static_context, self.context)
        self.assertIn("철근콘크리트조", result.briefing.context_summary)


if __name__ == "__main__":
    unittest.main()
