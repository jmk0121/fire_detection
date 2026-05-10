from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
MODELS_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"


def main() -> None:
    print("산불 탐지 모델 학습 파일입니다.")
    print("전처리된 데이터가 준비되면 여기서 모델을 학습하면 됩니다.")
    print(f"processed data: {PROCESSED_DIR}")
    print(f"models: {MODELS_DIR}")
    print(f"results: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
