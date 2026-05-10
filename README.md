# Fire Detection Project

기온, 습도, 풍향, 강수량 같은 날씨 데이터를 이용해서 산불 위험을 탐지하는 AI 프로젝트입니다.

처음에는 폴더를 아주 단순하게 시작하고, 필요할 때만 조금씩 늘리는 방식으로 구성했습니다.

## 폴더 구조

```text
fire_detection/
├─ data/
│  ├─ raw/          # 원본 CSV 데이터
│  └─ processed/    # 전처리 후 저장할 데이터
├─ src/             # 파이썬 코드
├─ models/          # 학습된 모델 파일
├─ results/         # 그래프, 예측 결과, 실험 결과
└─ README.md
```

## 각 폴더 설명

- `data/raw`: 처음 받은 원본 데이터를 그대로 둡니다.
- `data/processed`: 날짜 정리, 열 이름 정리, 결측치 처리 등을 마친 데이터를 저장합니다.
- `src`: 데이터를 읽고, 전처리하고, 모델을 학습하는 코드를 둡니다.
- `models`: 학습이 끝난 모델 파일을 저장합니다.
- `results`: 시각화 이미지, 평가 결과, 예측 결과를 저장합니다.

## 추천 작업 순서

1. `data/raw`에 있는 CSV 파일들을 확인합니다.
2. `src/prepare_data.py`에서 필요한 열만 정리합니다.
3. `src/train_model.py`에서 간단한 모델부터 학습합니다.
4. 결과를 `results`에 저장합니다.
5. 괜찮아지면 나중에 폴더를 더 세분화합니다.

## 현재 데이터

- `data/raw/강릉시 온도.csv`
- `data/raw/강릉시 습도.csv`
- `data/raw/강릉시 풍속 풍향.csv`
- `data/raw/강릉시 강수량.csv`
- `data/raw/forest_fire_incidents.csv`
- `data/processed/forest_fire_daily_national.csv`
- `data/processed/forest_fire_daily_gangneung.csv`

## 산불 데이터 가져오기

- `src/fetch_fire_data.ps1`: 산림청 산불 발생 API에서 원본 사건 데이터를 내려받습니다.
- `src/build_fire_labels.py`: 받아온 사건 데이터를 날짜 기준 일별 라벨로 정리합니다.

참고:

- 날씨 데이터 기간은 `2000-01-01`부터 `2026-05-09`까지입니다.
- 산불 API에서 실제로 내려온 사건 기간은 `2011-01-01`부터 `2025-12-31`까지입니다.
- 그래서 `2000-01-01`부터 `2010-12-31`까지의 산불 일별 라벨은 0으로 채워집니다.

## 다음에 추가하면 좋은 것

- 산불 발생 여부 라벨 데이터
- 하나의 표로 합친 통합 데이터셋
- 모델 성능 비교용 코드
