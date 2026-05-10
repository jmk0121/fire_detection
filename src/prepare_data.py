from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def main() -> None:
    csv_files = sorted(RAW_DIR.glob("*.csv"))

    print("원본 데이터 파일 목록")
    for file in csv_files:
        print(f"- {file.name}")

    print("\n다음 단계")
    print("1. 필요한 열 고르기")
    print("2. 날짜 형식 맞추기")
    print("3. 결측치 처리하기")
    print("4. 처리한 파일을 data/processed에 저장하기")


if __name__ == "__main__":
    main()
