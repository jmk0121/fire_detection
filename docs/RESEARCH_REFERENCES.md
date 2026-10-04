# 화재 현장 브리핑 구현 참고 연구

이 문서는 이름만 참고한 자료 목록이 아니라, 각 연구 결과를 구현의 어떤 결정에
사용했는지 기록한다.

## 1. 백드래프트 선별

### Falkenstein-Smith & Cleary (2022)

**A binary logistic regression model to evaluate backdraft phenomenon**

- [NIST 발행 페이지](https://www.nist.gov/publications/binary-logistic-regression-model-evaluate-backdraft-phenomenon)
- [논문 PDF](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935430)

연구 모델은 온도, 국소·전체 당량비, 산소농도를 사용했다. 측정 항목이 줄면 정확도가
낮아졌고, 두 위치에서 측정했을 때 성능이 개선됐다.

**구현 반영**

- 현재 시스템의 온도·MQ 비율만으로 백드래프트 확률을 계산하지 않는다.
- 산소농도, 연료–공기 혼합비, 구획 상태가 없으므로 결과를 `예측`이 아닌
  `현장 징후 확인`으로 표시한다.
- 빠른 센서 변화와 지하층 정보는 경보 확정값이 아니라 확인 순서를 올리는 선별값으로만
  사용한다.

### Falkenstein-Smith et al. (2022)

**Reduced-Scale Compartment Gaseous Fuels Backdraft Experiments**

- [NIST Technical Note 2183](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2183.pdf)

제한된 환기의 구획에서 고온의 연료성 가스에 신선한 공기가 유입될 때 백드래프트
위험이 형성되며, 검댕 낀 창과 개구부에서 밀고 당기는 맥동성 짙은 연기가 현장
징후로 제시된다.

**구현 반영**

- 최상위 행동에 검댕 낀 창, 유리 균열, 맥동성 짙은 연기, 화염 부재 확인을 포함했다.
- 징후 확인 전 문·창 개방이나 진입을 바로 권하지 않고, 개구부 정면 회피와 지휘관의
  환기·냉각 순서 조정을 먼저 제시한다.

## 2. 플래시오버 선별

### Wang et al. (2021)

**P-Flash – A Machine Learning-based Model for Flashover Prediction using Recovered Temperature Data**

- [NIST 발행 페이지](https://www.nist.gov/publications/p-flash-machine-learning-based-model-flashover-prediction-using-recovered-temperature)
- [논문 PDF](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=930425)

P-Flash는 단일 현재 온도가 아니라 여러 방의 열감지기 배열과 시간 데이터를 사용하고,
고온에서 감지기가 작동을 멈춘 상황까지 고려한다.

**구현 반영**

- 현재 단일 센서 흐름을 플래시오버 예측값으로 표시하지 않는다.
- 온도와 가스 비율이 함께 빠르게 변할 때 플래시오버의 관찰 전조를 먼저 확인하도록
  순위만 조정한다.

### Zhang et al. (2022)

**Real-time Forecast of Compartment Fire and Flashover based on Deep Learning**

- [NIST 발행 페이지](https://www.nist.gov/publications/real-time-forecast-compartment-fire-and-flashover-based-deep-learning)
- [DOI: 10.1016/j.firesaf.2022.103579](https://doi.org/10.1016/j.firesaf.2022.103579)

축소 구획 실험에서 온도 센서 네트워크와 딥러닝을 사용해 온도를 30초 앞서 예측하고
플래시오버를 약 20초 전에 예측했다. 연구 범위가 축소 실험과 제한된 화재 조건이라는
점도 명시되어 있다.

**구현 반영**

- 현재 화면의 30초 센서 구간을 순간값보다 우선 사용한다.
- 실제 예측 기능으로 발전시키려면 다지점 온도 센서, 구획 위치, 환기 조건, 실제 화재
  검증 데이터가 필요하다는 후속 개발 조건을 정했다.

## 3. 긴급 의사결정 UI

### Perry et al. (2013)

**The Application of Reduced-Processing Decision Support Systems to Facilitate the Acquisition of Decision-Making Skills**

- [DOI: 10.1177/0018720812467367](https://doi.org/10.1177/0018720812467367)

소방 지휘 의사결정 실험은 정보량을 줄이는 것만으로 정확도가 자동 향상되지 않으며,
사용자의 주의를 중요한 단서로 직접 이끌어야 함을 보여준다.

**구현 반영**

- 일반적인 `확인·보고` 문구보다 백드래프트·플래시오버의 관찰 징후를 우선 표시한다.
- 행동은 세 개만 보여주되 각 항목에 현재 센서 변화 근거를 함께 표시한다.

### Prasanna, Yang & King (2013)

**Guidance for developing human-computer interfaces for supporting fire emergency response**

- [DOI: 10.1057/rm.2013.3](https://doi.org/10.1057/rm.2013.3)

소방 대응 인터페이스는 현장 상황인식과 의사결정을 직접 지원하도록 실제 사용자 과업과
정보 요구를 중심으로 설계해야 한다.

**구현 반영**

- 피해등급, 센서 변화, 위험 징후, 행동, 건물정보 순으로 실제 판단 흐름을 고정했다.
- 기술명과 개발 설정 대신 소방관이 관찰하거나 실행할 표현을 사용했다.
- 선택된 출동 건물의 용도·지상/지하층수를 센서 추세와 같은 행동 문장에 넣고,
  공동주택처럼 재실 가능성이 중요한 용도는 대피 확인을 상위 세 항목으로 올렸다.
- 등록정보만으로 요구조자나 화재층을 추정하지 않고, 관계인 확인과 현장 보고 대상을
  구체화하는 데만 사용했다.

## 4. 현재 구현과 후속 센서 요구사항

현재 구현이 제공하는 것은 `위험현상 판정`이 아니라 `위험 징후 선별`이다. 다음 자료가
추가되기 전에는 백드래프트·플래시오버 확률을 화면에 표시하지 않는다.

- 구획별 다지점 온도와 센서 위치
- 산소농도와 연료–공기 혼합 상태를 설명할 수 있는 측정값
- 문·창·환기구 개방 상태와 압력 변화
- 실제 화재실험 또는 검증된 현장 데이터
- 위험현상별 정답 라벨과 외부 검증 결과

이 원칙은 제한된 입력에서 확정적 표현을 만드는 오류를 막고, 현재 시스템이 할 수 있는
가장 실용적인 역할인 `무엇을 먼저 관찰하고 어떻게 안전을 확보할지`에 집중하게 한다.
