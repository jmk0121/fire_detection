# 화재 현장 피해등급 예측 및 Gemini 브리핑

ESP32의 온도·습도·가스 센서 시계열과 CSV의 건물 정적정보를 함께 사용해
LSTM 피해등급을 예측하고, 같은 건물정보와 예측 결과를 Gemini API에 전달해
짧은 현장 브리핑을 생성하는 교육용 프로젝트입니다.

> 이 프로젝트는 합성 데이터 기반 프로토타입입니다. 실제 화재 현장의 지휘,
> 진입, 대피 또는 진압 결정을 대신하지 않습니다.

## 처리 흐름

```text
ESP32 센서 → 최근 16개 샘플 → LSTM 피해등급
                         ↘ 선택한 CSV 건물정보 한 행
예측 결과 + 센서 요약 + 동일한 건물정보 → 조건별 안전 규칙 선택
                                          ↘ Gemini/데모 현장 브리핑
```

`--row` 또는 API의 `context_row`로 선택한 CSV 한 행은 한 번만 읽습니다.
이 행의 정적 feature가 LSTM 전처리에 사용되고, 동일한 값을
`static_context_used_by_lstm`이라는 이름으로 Gemini에도 전달합니다.
이 선택 행을 출동 대상 건물로 보고 용도·층수·지하층·구조를 현재 30초 센서 추세와
결합해 행동 문구와 표시 우선순위에도 반영합니다.

## 설치

Python 3.10 환경을 기준으로 합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_lstm.txt
```

저장된 `lstm_preprocessing.joblib`은 scikit-learn 1.6.1에서 생성되어 요구사항도
같은 버전으로 고정했습니다.

## Gemini API 키 설정

1. Google AI Studio에서 Gemini API 키를 발급합니다.
2. `.env.example`을 `.env`로 복사합니다.
3. `.env`의 키를 실제 값으로 변경합니다.

```powershell
Copy-Item .env.example .env
```

```dotenv
GEMINI_API_KEY=발급받은_키
GEMINI_MODEL=gemini-3.5-flash-lite
```

`.env`는 Git에서 제외됩니다. 키를 코드, README, CSV 또는 Git 커밋에 넣지 마세요.
무료 등급 요청은 모델별 할당량 제한을 받으며 정책이 바뀔 수 있습니다.
또한 무료 등급에 실제 개인식별정보나 민감한 현장정보를 전송하지 마세요.

키가 없으면 LSTM 예측, 30초 센서 변화, 선택된 건물정보와 조건별 현장 대응
참고 항목을 조합한 자연스러운 데모 브리핑이 반환됩니다. 이 경우 응답의
`briefing.source`는 `demo`입니다.
API 호출이 실패해도 LSTM 예측은 계속 실행되고 같은 형식의 대체 브리핑이
반환됩니다.

## REST API 실행

```powershell
python -m uvicorn app.main:app --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- 상태 확인: `GET http://127.0.0.1:8000/api/v1/health`
- 분석: `POST http://127.0.0.1:8000/api/v1/analyze`

## 현장 브리핑 UI

API를 실행한 뒤 `http://127.0.0.1:8000`으로 접속하면 현장 브리핑
대시보드가 열립니다. 별도 프런트엔드 설치 과정은 없습니다.

- 별도 조작 없이 최신 센서 스냅샷을 자동 확인해 화면을 갱신합니다.
- 피해등급·신뢰도, 현장 요약, 최근 30초 센서 변화, 즉시 확인할 행동 세 개,
  건물 핵심정보만 한 방향으로 읽도록 구성했습니다.
- 행동 문장은 선택된 건물의 용도와 층수를 직접 포함하며, 공동주택 등 재실 가능
  용도에서는 재실자·대피 확인을 상위 항목으로 표시합니다.
- 개발 중 센서 스냅샷이 없으면 내부 시험 입력으로 전체 분석 흐름을 확인합니다.
  실제 센서 데이터가 들어오면 같은 화면에서 자동 전환됩니다.

### HCI 설계 원칙

사용자·과업 분석, 원칙별 구현 근거와 사용성 평가 계획은
[`docs/HCI_DESIGN.md`](docs/HCI_DESIGN.md)에 정리했습니다.

- **맥락 중심 설계**: 소음, 장갑, 낮은 시인성, 시간 압박이 있는 현장을 사용
  환경으로 정의했습니다.
- **인지 부하 최소화**: 피해등급 → 요약 → 센서 → 행동 → 건물 순서로 읽으며,
  행동은 상위 세 개만 제공합니다.
- **기억보다 인식**: 현재 센서값과 최근 30초 변화 방향을 함께 표시합니다.
- **색상 외 중복 표현**: 등급 숫자, 화살표, 부호, 우선순위 문구를 색상과 함께
  사용합니다.
- **최소 조작**: 설정과 모드 선택을 없애고 최신 결과를 자동 갱신합니다.
- **접근성**: 의미 있는 제목 구조, 본문 바로가기, 실시간 영역 알림, 키보드 초점,
  동작 줄이기 설정을 지원합니다.
- **평가 가능성**: 과업 완료 시간, 정답률, 되읽기 횟수, 주관적 정신적 부담을
  기준으로 개선 효과를 검증하도록 평가 계획을 정의했습니다.

분석 요청에는 모델이 요구하는 16개 센서 샘플을 보냅니다.

브리핑 응답은 다음 순서로 구성됩니다.

- `situation_summary`: 센서 관측과 모델 추론을 구분한 현장 설명
- `context_summary`: 모델과 LLM이 공통 사용한 건물 구조·층수·용도 정보
- `operational_summary`: 즉시 확인 항목을 앞세운 짧은 지휘 브리핑
- `operational_guidance`: 우선순위, 행동, 이유, 발동 조건, SOP 근거가 포함된 목록
- `uncertainty`: 모델이 알 수 없는 정보와 사용 한계

```json
{
  "context_row": 0,
  "generate_briefing": true,
  "samples": [
    {"temperature": 20.0, "humidity": 50.0, "gas1_ratio": 1.0, "gas2_ratio": 1.0},
    {"temperature": 20.5, "humidity": 49.8, "gas1_ratio": 1.1, "gas2_ratio": 1.0},
    {"temperature": 21.0, "humidity": 49.5, "gas1_ratio": 1.1, "gas2_ratio": 1.1},
    {"temperature": 21.5, "humidity": 49.2, "gas1_ratio": 1.2, "gas2_ratio": 1.1},
    {"temperature": 22.0, "humidity": 49.0, "gas1_ratio": 1.2, "gas2_ratio": 1.2},
    {"temperature": 22.5, "humidity": 48.8, "gas1_ratio": 1.3, "gas2_ratio": 1.2},
    {"temperature": 23.0, "humidity": 48.5, "gas1_ratio": 1.3, "gas2_ratio": 1.3},
    {"temperature": 23.5, "humidity": 48.2, "gas1_ratio": 1.4, "gas2_ratio": 1.3},
    {"temperature": 24.0, "humidity": 48.0, "gas1_ratio": 1.4, "gas2_ratio": 1.4},
    {"temperature": 24.5, "humidity": 47.8, "gas1_ratio": 1.5, "gas2_ratio": 1.4},
    {"temperature": 25.0, "humidity": 47.5, "gas1_ratio": 1.5, "gas2_ratio": 1.5},
    {"temperature": 25.5, "humidity": 47.2, "gas1_ratio": 1.6, "gas2_ratio": 1.5},
    {"temperature": 26.0, "humidity": 47.0, "gas1_ratio": 1.6, "gas2_ratio": 1.6},
    {"temperature": 26.5, "humidity": 46.8, "gas1_ratio": 1.7, "gas2_ratio": 1.6},
    {"temperature": 27.0, "humidity": 46.5, "gas1_ratio": 1.7, "gas2_ratio": 1.7},
    {"temperature": 27.5, "humidity": 46.2, "gas1_ratio": 1.8, "gas2_ratio": 1.7}
  ]
}
```

## ESP32 실시간 실행

```powershell
python realtime_predict_lstm.py --port COM6 --row 0
```

- LSTM은 센서 샘플을 받을 때마다 실행됩니다.
- Gemini는 등급이 바뀌거나 기본 30초 간격이 지났을 때만 호출됩니다.
- Gemini 호출은 별도 스레드에서 수행되어 센서 수집을 막지 않습니다.
- 설명 로그는 `live_llm_briefings.jsonl`에 기록됩니다.
- 최신 대시보드 데이터는 `live_dashboard.json`에 원자적으로 갱신됩니다.
- Gemini 없이 실행하려면 `--no-llm`을 사용합니다.

```powershell
python realtime_predict_lstm.py --port COM6 --row 0 --no-llm
```

## 현장 대응 참고 항목과 등급 정의

- `data/approved_checklists.json`: 코드가 조건에 따라 선택하는 구조화된 현장 대응 참고 항목
- `data/grade_definitions.json`: 피해등급 0·1·2의 의미
- `app/prompts/fire_briefing_v1.txt`: Gemini가 따라야 하는 생성 규칙
- `docs/RESEARCH_REFERENCES.md`: 구현에 실제 반영한 화재거동·의사결정지원 연구

현장 대응 항목은 소방청의
[「재난현장 표준작전절차 및 표준작전절차 안전관리기법」](https://daegu.go.kr/cmsh/daegu.go.kr/119/files/%EC%9E%AC%EB%82%9C%ED%98%84%EC%9E%A5%ED%91%9C%EC%A4%80%EC%9E%91%EC%A0%84%EC%A0%88%EC%B0%A8.pdf)
중 상황평가, 화재 대응, 현장 안전, 지하층 활동 내용을 바탕으로
교육용으로 짧게 정리했습니다. 백드래프트와 플래시오버의 현장 징후는
[NIST Technical Note 2183](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2183.pdf)과
[미국 소방청 초기 지휘 교재](https://apps.usfa.fema.gov/ax/sm/sm_0457.pdf)를
참고했습니다. 온도·가스 동시 급상승은 위험 현상을 확정하는 값이 아니라 현장 징후를
우선 확인하게 하는 선별 신호로만 사용합니다. Gemini는 코드가 선택한 항목을 요약할 수만 있고,
목록에 없는 진입·방수·환기·소화약제 전술을 새로 만들지 못하도록 프롬프트와
응답 스키마를 제한했습니다.

현재의 급변 기준은 합성 데이터 흐름을 확인하기 위한 프로젝트 선별값이며 물리적
백드래프트·플래시오버 임계값이 아닙니다. 산소농도와 구획별 열감지기 데이터가 추가되기
전까지 화면은 위험 확률을 계산하지 않고 관찰해야 할 현장 징후만 우선 제시합니다.

현재 등급 의미는 원본 데이터 생성 기준이 확인되지 않아 임시 이름으로 두었습니다.
실제 의미를 확인한 뒤 `grade_definitions.json`을 수정해야 합니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

테스트에서는 실제 Gemini API를 호출하지 않고, LSTM과 Gemini가 동일한 정적정보를
공유하는지와 API 키가 없을 때 실제 입력 기반 데모 문구로 전환되는지를 검사합니다.

## 센서 기반 안전 연구실

`http://127.0.0.1:8000/research`에서 공개 실험 10건을 재생합니다. 기존 홈 화면의
**안전 연구실** 링크로도 열 수 있습니다. 고온층 온도 추세, IMU 보행 추정,
강재 보 변형 감지를 각각 비교하며 API 키 없이 동작합니다.

- [구현 전 계획](docs/SAFETY_LAB_PLAN.md)
- [구현·검증 결과와 HCI 검토](docs/SAFETY_LAB_REVIEW.md)
- [출처·이용 조건](data/research/NOTICE.md)

가공된 JSON/CSV는 포함되어 있습니다. 원본 재다운로드와 결과 재생성:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_research.txt
.\.venv\Scripts\python.exe -X utf8 scripts\fetch_research_data.py
.\.venv\Scripts\python.exe -X utf8 scripts\prepare_research_data.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

원본은 `data/research/raw`에 보관하고 Git에서는 제외합니다. 파생 파일은
`data/research/processed`, 원본 URL·SHA-256·단위·선택 채널은 출처 목록과 실험 메타데이터에
남깁니다. 이 연구실은 저장 데이터 재생이며 새 ESP32 실시간 수집 기능은 아닙니다.
600°C는 대리지표, 구조 경보는 변형 이상, 위치는 오차가 누적되는 추정입니다.

브라우저 점검은 선택적으로 `pip install playwright` 후 설치된 Edge를 이용하여
`python tests/browser_research.py`로 실행합니다. 서버를 먼저 켜야 합니다.
