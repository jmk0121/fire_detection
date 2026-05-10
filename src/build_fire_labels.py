from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

INCIDENTS_FILE = RAW_DIR / "forest_fire_incidents.csv"
NATIONAL_DAILY_FILE = PROCESSED_DIR / "forest_fire_daily_national.csv"
GANGNEUNG_DAILY_FILE = PROCESSED_DIR / "forest_fire_daily_gangneung.csv"


def read_weather_dates() -> list[str]:
    weather_files = sorted(path for path in RAW_DIR.glob("*.csv") if path.name != INCIDENTS_FILE.name)
    if not weather_files:
        raise ValueError("날씨 데이터 CSV 파일을 찾지 못했습니다.")

    dates: list[str] = []
    with weather_files[0].open("r", encoding="utf-8", newline="") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or not line[0].isdigit():
                continue

            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue

            date_text = parts[2]
            if len(date_text) == 10 and date_text[4] == "-" and date_text[7] == "-":
                dates.append(date_text)

    return dates


def read_incidents() -> list[dict[str, str]]:
    with INCIDENTS_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_gangneung(row: dict[str, str]) -> bool:
    location_text = " ".join(
        [
            row.get("locsi", ""),
            row.get("locgungu", ""),
            row.get("locmenu", ""),
            row.get("locdong", ""),
        ]
    )
    return "강릉" in location_text


def build_rows(weather_dates: list[str], incidents: list[dict[str, str]], only_gangneung: bool) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"fire_count": 0.0, "damagearea_total": 0.0})

    for row in incidents:
        if only_gangneung and not is_gangneung(row):
            continue

        date_text = row["date"]
        grouped[date_text]["fire_count"] += 1
        grouped[date_text]["damagearea_total"] += to_float(row.get("damagearea", "0"))

    rows: list[dict[str, str]] = []
    for date_text in weather_dates:
        fire_count = int(grouped[date_text]["fire_count"])
        rows.append(
            {
                "date": date_text,
                "fire_occurred": "1" if fire_count > 0 else "0",
                "fire_count": str(fire_count),
                "damagearea_total": f"{grouped[date_text]['damagearea_total']:.2f}",
            }
        )

    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["date", "fire_occurred", "fire_count", "damagearea_total"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    weather_dates = read_weather_dates()
    incidents = read_incidents()

    national_rows = build_rows(weather_dates, incidents, only_gangneung=False)
    gangneung_rows = build_rows(weather_dates, incidents, only_gangneung=True)

    write_rows(NATIONAL_DAILY_FILE, national_rows)
    write_rows(GANGNEUNG_DAILY_FILE, gangneung_rows)

    print(f"saved: {NATIONAL_DAILY_FILE}")
    print(f"saved: {GANGNEUNG_DAILY_FILE}")


if __name__ == "__main__":
    main()
