import argparse
import csv
import json
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import serial

from app.config import Settings
from app.schemas import SafetyBriefing, SensorSample
from app.services.briefing import GeminiBriefingService
from app.services.predictor import FirePredictor
from app.services.safety_rules import SafetyRuleEngine
from app.services.sensor_summary import summarize_sensor_window


LOG_PATH = "live_lstm_predictions.csv"
BRIEFING_LOG_PATH = "live_llm_briefings.jsonl"
BAUD = 115200


def read_packet(ser):
    """Read one ESP32 line: DATA,temperature,humidity,gas1_raw,gas2_raw."""
    raw = ser.readline()
    if not raw:
        return None

    line = raw.decode("utf-8", errors="ignore").strip()
    if not line.startswith("DATA,"):
        return None

    parts = line.split(",")
    if len(parts) != 5:
        return None

    try:
        return {
            "temperature": float(parts[1]),
            "humidity": float(parts[2]),
            "gas1_raw": float(parts[3]),
            "gas2_raw": float(parts[4]),
        }
    except ValueError:
        return None


def collect_baseline(ser, seconds):
    gas1 = []
    gas2 = []

    print(f"\n[1/3] MQ baseline 측정: {seconds}초")
    print("이 시간에는 센서 주변을 평상시 상태로 유지하세요.")
    start = time.time()

    while time.time() - start < seconds:
        packet = read_packet(ser)
        if packet is None:
            continue

        gas1.append(packet["gas1_raw"])
        gas2.append(packet["gas2_raw"])
        print(
            f"\rSamples={len(gas1):3d} "
            f"MQ1={packet['gas1_raw']:.0f} "
            f"MQ2={packet['gas2_raw']:.0f}",
            end="",
            flush=True,
        )

    print()
    if len(gas1) < 5:
        raise RuntimeError("ESP32 센서 데이터를 충분히 받지 못했습니다.")

    baseline1 = float(np.median(gas1))
    baseline2 = float(np.median(gas2))
    if baseline1 <= 0 or baseline2 <= 0:
        raise RuntimeError("MQ baseline 값이 비정상입니다.")

    print(f"MQ1 baseline = {baseline1:.2f}")
    print(f"MQ2 baseline = {baseline2:.2f}")
    return baseline1, baseline2


def print_briefing(briefing: SafetyBriefing) -> None:
    title = {
        "gemini": "GEMINI 현장 브리핑",
        "demo": "DEMO 현장 브리핑",
        "fallback": "DEMO 대체 브리핑",
    }[briefing.source]
    print(f"\n[{title}]")
    print(briefing.headline)
    print("\n[현장 설명]")
    print(briefing.situation_summary)
    print(briefing.context_summary)
    print("\n[지휘 우선순위 요약]")
    print(briefing.operational_summary)
    print("\n[조건별 현장 대응 참고]")
    for item in briefing.operational_guidance:
        print(f"- [{item.priority}/{item.category}] {item.title}")
        print(f"  {item.action}")
        print(f"  이유: {item.rationale}")
        print(f"  적용 조건: {item.trigger} | 근거: {item.basis}")
    print(f"주의: {briefing.uncertainty}")
    if briefing.source != "gemini":
        print(f"[생성 방식] {briefing.generation_note}")
    print("-" * 90)


def write_briefing_log(
    context_row: int,
    grade_code: str,
    briefing: SafetyBriefing,
) -> None:
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "context_row": context_row,
        "grade_code": grade_code,
        "briefing": briefing.model_dump(),
    }
    with Path(BRIEFING_LOG_PATH).open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="예: COM6")
    parser.add_argument(
        "--row",
        type=int,
        default=0,
        help="모델과 Gemini가 함께 사용할 CSV 정적정보 행 번호",
    )
    parser.add_argument("--baseline-seconds", type=int, default=60)
    parser.add_argument(
        "--llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Gemini 브리핑 활성화. 끄려면 --no-llm",
    )
    parser.add_argument(
        "--llm-interval-seconds",
        type=float,
        default=None,
        help="동일 등급에서 브리핑을 다시 생성할 최소 간격",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    llm_interval = (
        args.llm_interval_seconds
        if args.llm_interval_seconds is not None
        else settings.llm_min_interval_seconds
    )
    predictor = FirePredictor(
        data_path=settings.data_path,
        model_path=settings.model_path,
        preprocess_path=settings.preprocess_path,
    )
    context = predictor.get_context(args.row)
    safety_rules = SafetyRuleEngine(
        settings.checklist_path,
        settings.low_confidence_threshold,
    )
    briefing_service = GeminiBriefingService(settings)

    print(f"\n[STATIC] CSV row = {args.row}")
    print("아래 한 행이 LSTM 정적 입력과 Gemini 설명 입력에 함께 사용됩니다.")
    for column, value in context.values.items():
        print(f"{column}: {value}")

    print("\n[MODEL] LSTM 모델 로드 완료")
    if args.llm:
        if briefing_service.is_configured:
            print(f"[LLM] Gemini 활성화: {settings.gemini_model}")
        else:
            print("[LLM] API 키가 없어 실제 입력 기반 데모 브리핑을 사용합니다.")

    try:
        ser = serial.Serial(args.port, BAUD, timeout=1)
    except serial.SerialException as error:
        raise RuntimeError(
            f"{args.port}를 열 수 없습니다. "
            "Arduino Serial Monitor를 닫고 COM 포트를 확인하세요."
        ) from error

    time.sleep(2.5)
    ser.reset_input_buffer()

    log_file = None
    briefing_executor = ThreadPoolExecutor(max_workers=1)
    briefing_future: Future | None = None
    pending_briefing_grade: str | None = None
    last_submitted_grade: str | None = None
    last_submitted_at = 0.0

    try:
        baseline1, baseline2 = collect_baseline(ser, args.baseline_seconds)
        window = deque(maxlen=predictor.sequence_length)

        print(
            f"\n[2/3] 최근 약 30초 데이터 수집 "
            f"({predictor.sequence_length} samples)"
        )
        print("[3/3] window가 채워지면 LSTM 실시간 예측 시작\n")

        log_exists = Path(LOG_PATH).exists()
        log_file = open(LOG_PATH, "a", newline="", encoding="utf-8-sig")
        probability_headers = [
            f"prob_grade_{label}" for label in predictor.label_encoder.classes_
        ]
        writer = csv.writer(log_file)
        if not log_exists:
            writer.writerow(
                [
                    "timestamp",
                    "static_row",
                    "temperature",
                    "humidity",
                    "gas1_raw",
                    "gas2_raw",
                    "gas1_ratio",
                    "gas2_ratio",
                    "prediction",
                    "confidence",
                    *probability_headers,
                ]
            )

        while True:
            if briefing_future is not None and briefing_future.done():
                briefing = briefing_future.result()
                print_briefing(briefing)
                write_briefing_log(
                    args.row,
                    pending_briefing_grade or "unknown",
                    briefing,
                )
                briefing_future = None
                pending_briefing_grade = None

            packet = read_packet(ser)
            if packet is None:
                continue

            gas1_ratio = packet["gas1_raw"] / baseline1
            gas2_ratio = packet["gas2_raw"] / baseline2
            window.append(
                SensorSample(
                    temperature=packet["temperature"],
                    humidity=packet["humidity"],
                    gas1_ratio=gas1_ratio,
                    gas2_ratio=gas2_ratio,
                )
            )

            if len(window) < predictor.sequence_length:
                print(
                    f"\rWindow {len(window):02d}/{predictor.sequence_length} | "
                    f"T={packet['temperature']:.1f}C | "
                    f"H={packet['humidity']:.1f}% | "
                    f"G1={gas1_ratio:.2f}x | G2={gas2_ratio:.2f}x",
                    end="",
                    flush=True,
                )
                continue

            samples = list(window)
            prediction = predictor.predict(samples, context)
            probs_text = " | ".join(
                f"{label}={probability * 100:.1f}%"
                for label, probability in prediction.probabilities.items()
            )

            print()
            print(
                f"T={packet['temperature']:.1f}C | "
                f"H={packet['humidity']:.1f}% | "
                f"MQ1={packet['gas1_raw']:.0f}(x{gas1_ratio:.2f}) | "
                f"MQ2={packet['gas2_raw']:.0f}(x{gas2_ratio:.2f})"
            )
            print(
                f">>> LSTM 피해등급 = {prediction.grade_code} | "
                f"최고확률 = {prediction.confidence * 100:.1f}%"
            )
            print(probs_text)
            print("-" * 90)

            writer.writerow(
                [
                    datetime.now().isoformat(timespec="seconds"),
                    args.row,
                    packet["temperature"],
                    packet["humidity"],
                    packet["gas1_raw"],
                    packet["gas2_raw"],
                    gas1_ratio,
                    gas2_ratio,
                    prediction.grade_code,
                    prediction.confidence,
                    *prediction.probabilities.values(),
                ]
            )
            log_file.flush()

            now = time.monotonic()
            should_generate = (
                last_submitted_grade != prediction.grade_code
                or now - last_submitted_at >= llm_interval
            )
            if args.llm and briefing_future is None and should_generate:
                summary = summarize_sensor_window(
                    samples,
                    settings.sensor_sample_interval_seconds,
                )
                operational_guidance = safety_rules.select(
                    context.values,
                    prediction,
                    summary,
                )
                briefing_future = briefing_executor.submit(
                    briefing_service.generate,
                    prediction,
                    summary,
                    context.values,
                    operational_guidance,
                )
                pending_briefing_grade = prediction.grade_code
                last_submitted_grade = prediction.grade_code
                last_submitted_at = now

    except KeyboardInterrupt:
        print("\n실시간 예측 종료")
    finally:
        ser.close()
        if log_file is not None:
            log_file.close()
        briefing_executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
