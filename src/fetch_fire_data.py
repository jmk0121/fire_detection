from __future__ import annotations

import csv
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path


SERVICE_KEY = "6d6f177f3a50b5bbf41528cd764e4db5b684e78fc427885555ffd201e68befe7"
BASE_URL = "https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice"

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

INCIDENTS_FILE = RAW_DIR / "forest_fire_incidents.csv"
NATIONAL_DAILY_FILE = PROCESSED_DIR / "forest_fire_daily_national.csv"
GANGNEUNG_DAILY_FILE = PROCESSED_DIR / "forest_fire_daily_gangneung.csv"


def read_weather_dates() -> list[str]:
    dates: list[str] = []

    weather_files = sorted(path for path in RAW_DIR.glob("*.csv") if path.name != INCIDENTS_FILE.name)
    if not weather_files:
        raise ValueError("날씨 데이터 CSV 파일을 찾지 못했습니다.")

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

    if not dates:
        raise ValueError("날씨 데이터에서 날짜를 찾지 못했습니다.")

    return dates


def fetch_api_page(page_no: int, num_rows: int, start_date: str, end_date: str) -> tuple[int, list[dict[str, str]]]:
    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": str(page_no),
        "numOfRows": str(num_rows),
        "searchStDt": start_date.replace("-", ""),
        "searchEdDt": end_date.replace("-", ""),
    }
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"

    with urllib.request.urlopen(url, timeout=60) as response:
        xml_bytes = response.read()

    root = ET.fromstring(xml_bytes)

    result_code = root.findtext("./header/resultCode", default="")
    result_msg = root.findtext("./header/resultMsg", default="")
    if result_code != "00":
        raise RuntimeError(f"API 호출 실패: {result_code} {result_msg}")

    total_count = int(root.findtext("./body/totalCount", default="0"))

    items: list[dict[str, str]] = []
    for item in root.findall("./body/items/item"):
        row: dict[str, str] = {}
        for child in item:
            row[child.tag] = (child.text or "").strip()
        items.append(row)

    return total_count, items


def fetch_all_incidents(start_date: str, end_date: str) -> list[dict[str, str]]:
    num_rows = 500
    total_count, first_items = fetch_api_page(1, num_rows, start_date, end_date)
    incidents = list(first_items)

    total_pages = math.ceil(total_count / num_rows)
    print(f"산불 API 전체 건수: {total_count}")
    print(f"페이지 수: {total_pages}")

    for page_no in range(2, total_pages + 1):
        _, items = fetch_api_page(page_no, num_rows, start_date, end_date)
        incidents.extend(items)
        print(f"- {page_no}/{total_pages} 페이지 수집 완료")

    return incidents


def to_date_text(row: dict[str, str]) -> str:
    year = row.get("startyear", "").zfill(4)
    month = row.get("startmonth", "").zfill(2)
    day = row.get("startday", "").zfill(2)
    return f"{year}-{month}-{day}"


def to_float(value: str) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def is_gangneung_incident(row: dict[str, str]) -> bool:
    locsi = row.get("locsi", "")
    locgungu = row.get("locgungu", "")
    locmenu = row.get("locmenu", "")
    locdong = row.get("locdong", "")
    location_text = " ".join([locsi, locgungu, locmenu, locdong])
    return "강릉" in location_text


def write_incidents_csv(path: Path, incidents: list[dict[str, str]]) -> None:
    fieldnames = [
        "date",
        "startyear",
        "startmonth",
        "startday",
        "starttime",
        "endyear",
        "endmonth",
        "endday",
        "endtime",
        "locsi",
        "locgungu",
        "locmenu",
        "locdong",
        "locbunji",
        "firecause",
        "damagearea",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in incidents:
            output = {name: row.get(name, "") for name in fieldnames}
            output["date"] = to_date_text(row)
            writer.writerow(output)


def build_daily_rows(weather_dates: list[str], incidents: list[dict[str, str]], only_gangneung: bool) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"fire_count": 0.0, "damagearea_total": 0.0})

    for row in incidents:
        if only_gangneung and not is_gangneung_incident(row):
            continue

        date_text = to_date_text(row)
        grouped[date_text]["fire_count"] += 1
        grouped[date_text]["damagearea_total"] += to_float(row.get("damagearea", "0"))

    daily_rows: list[dict[str, str]] = []
    for date_text in weather_dates:
        fire_count = int(grouped[date_text]["fire_count"])
        damagearea_total = grouped[date_text]["damagearea_total"]
        daily_rows.append(
            {
                "date": date_text,
                "fire_occurred": "1" if fire_count > 0 else "0",
                "fire_count": str(fire_count),
                "damagearea_total": f"{damagearea_total:.2f}",
            }
        )

    return daily_rows


def write_daily_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["date", "fire_occurred", "fire_count", "damagearea_total"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    weather_dates = read_weather_dates()
    start_date = weather_dates[0]
    end_date = weather_dates[-1]

    print(f"날씨 데이터 기간: {start_date} ~ {end_date}")
    incidents = fetch_all_incidents(start_date, end_date)

    incidents.sort(
        key=lambda row: datetime.strptime(
            f"{to_date_text(row)} {row.get('starttime', '00:00:00') or '00:00:00'}",
            "%Y-%m-%d %H:%M:%S",
        )
    )

    write_incidents_csv(INCIDENTS_FILE, incidents)

    national_daily = build_daily_rows(weather_dates, incidents, only_gangneung=False)
    gangneung_daily = build_daily_rows(weather_dates, incidents, only_gangneung=True)

    write_daily_csv(NATIONAL_DAILY_FILE, national_daily)
    write_daily_csv(GANGNEUNG_DAILY_FILE, gangneung_daily)

    print(f"원본 사건 파일 저장: {INCIDENTS_FILE}")
    print(f"일별 전국 파일 저장: {NATIONAL_DAILY_FILE}")
    print(f"일별 강릉 연계 파일 저장: {GANGNEUNG_DAILY_FILE}")


if __name__ == "__main__":
    main()
