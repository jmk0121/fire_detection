import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.utils.class_weight import compute_class_weight
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Concatenate, Dense, Dropout, Input, LSTM
from tensorflow.keras.models import Model


# ============================================================
# 파일/설정
# ============================================================
DATA_PATH = "fire_training_synthetic(1).csv"
MODEL_PATH = "fire_lstm.keras"
PREPROCESS_PATH = "lstm_preprocessing.joblib"

TARGET = "피해등급"
SEQUENCE_LENGTH = 16  # 2초 간격 16개 ~= 약 30초
RANDOM_STATE = 42

SENSOR_FEATURES = [
    "sensor_temperature",
    "sensor_humidity",
    "gas1_ratio",
    "gas2_ratio",
    "temp_rise_30s",
    "gas1_ratio_change_30s",
    "gas2_ratio_change_30s",
    "gas1_max_ratio_30s",
    "gas2_max_ratio_30s",
]

SENSOR_CHANNELS = [
    "temperature",
    "humidity",
    "gas1_ratio",
    "gas2_ratio",
]


# ============================================================
# CSV의 30초 요약값 -> LSTM용 16-step sequence 복원
# CSV 내용 자체는 변경하지 않는다.
# ============================================================
def piecewise_peak_series(start, end, peak, n=SEQUENCE_LENGTH):
    start = float(start)
    end = float(end)
    peak = max(float(peak), start, end)

    peak_idx = n // 2

    left = np.linspace(start, peak, peak_idx + 1, dtype=np.float32)
    right = np.linspace(peak, end, n - peak_idx, dtype=np.float32)

    # peak 중복 제거 후 정확히 n개
    return np.concatenate([left[:-1], right]).astype(np.float32)


def build_sequence_from_row(row):
    temp_now = float(row["sensor_temperature"])
    humidity_now = float(row["sensor_humidity"])

    gas1_now = float(row["gas1_ratio"])
    gas2_now = float(row["gas2_ratio"])

    temp_start = temp_now - float(row["temp_rise_30s"])
    gas1_start = gas1_now - float(row["gas1_ratio_change_30s"])
    gas2_start = gas2_now - float(row["gas2_ratio_change_30s"])

    # ratio는 음수가 되지 않도록 제한
    gas1_start = max(gas1_start, 0.0)
    gas2_start = max(gas2_start, 0.0)

    temp_series = np.linspace(
        temp_start,
        temp_now,
        SEQUENCE_LENGTH,
        dtype=np.float32,
    )

    # 습도 변화량 컬럼이 없으므로 현재값을 30초 동안 유지한 것으로 사용
    humidity_series = np.full(
        SEQUENCE_LENGTH,
        humidity_now,
        dtype=np.float32,
    )

    gas1_series = piecewise_peak_series(
        gas1_start,
        gas1_now,
        row["gas1_max_ratio_30s"],
    )

    gas2_series = piecewise_peak_series(
        gas2_start,
        gas2_now,
        row["gas2_max_ratio_30s"],
    )

    return np.stack(
        [temp_series, humidity_series, gas1_series, gas2_series],
        axis=1,
    ).astype(np.float32)


def make_ohe():
    # scikit-learn 버전 호환
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


# ============================================================
# 데이터 로드
# ============================================================
tf.keras.utils.set_random_seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

df = pd.read_csv(DATA_PATH)

required = [TARGET, *SENSOR_FEATURES]
missing = [col for col in required if col not in df.columns]
if missing:
    raise ValueError(f"CSV에 필요한 컬럼이 없습니다: {missing}")

# sensor_data_source는 데이터 출처 표시이므로 모델 feature에서 제외
STATIC_FEATURES = [
    col
    for col in df.columns
    if col not in [TARGET, "sensor_data_source", *SENSOR_FEATURES]
]

categorical_features = (
    df[STATIC_FEATURES]
    .select_dtypes(include=["object", "category"])
    .columns
    .tolist()
)

numeric_features = [
    col for col in STATIC_FEATURES if col not in categorical_features
]

print("데이터 수:", len(df))
print("정적 feature 수:", len(STATIC_FEATURES))
print("범주형 feature:", len(categorical_features))
print("수치형 feature:", len(numeric_features))
print("LSTM sequence shape: (16, 4)")

# ============================================================
# 라벨 인코딩
# ============================================================
label_encoder = LabelEncoder()
y = label_encoder.fit_transform(df[TARGET])

# 먼저 index를 분리해서 전처리 leakage 방지
all_idx = np.arange(len(df))

train_idx, temp_idx = train_test_split(
    all_idx,
    test_size=0.20,
    random_state=RANDOM_STATE,
    stratify=y,
)

val_idx, test_idx = train_test_split(
    temp_idx,
    test_size=0.50,
    random_state=RANDOM_STATE,
    stratify=y[temp_idx],
)

# ============================================================
# 정적 feature 전처리
# ============================================================
static_preprocessor = ColumnTransformer(
    transformers=[
        (
            "cat",
            make_ohe(),
            categorical_features,
        ),
        (
            "num",
            StandardScaler(),
            numeric_features,
        ),
    ],
    remainder="drop",
)

X_static_train = static_preprocessor.fit_transform(
    df.iloc[train_idx][STATIC_FEATURES]
).astype(np.float32)

X_static_val = static_preprocessor.transform(
    df.iloc[val_idx][STATIC_FEATURES]
).astype(np.float32)

X_static_test = static_preprocessor.transform(
    df.iloc[test_idx][STATIC_FEATURES]
).astype(np.float32)

# ============================================================
# LSTM sensor sequence 생성
# ============================================================
print("센서 sequence 생성 중...")

sequences = np.stack(
    [build_sequence_from_row(row) for _, row in df.iterrows()],
    axis=0,
).astype(np.float32)

X_seq_train = sequences[train_idx]
X_seq_val = sequences[val_idx]
X_seq_test = sequences[test_idx]

# 센서 채널 스케일링: train 데이터에만 fit
sensor_scaler = StandardScaler()
sensor_scaler.fit(X_seq_train.reshape(-1, len(SENSOR_CHANNELS)))


def scale_sequences(x):
    shape = x.shape
    scaled = sensor_scaler.transform(
        x.reshape(-1, len(SENSOR_CHANNELS))
    )
    return scaled.reshape(shape).astype(np.float32)


X_seq_train = scale_sequences(X_seq_train)
X_seq_val = scale_sequences(X_seq_val)
X_seq_test = scale_sequences(X_seq_test)

# ============================================================
# y
# ============================================================
y_train = y[train_idx]
y_val = y[val_idx]
y_test = y[test_idx]

# 클래스 불균형 보정
unique_classes = np.unique(y_train)
weights = compute_class_weight(
    class_weight="balanced",
    classes=unique_classes,
    y=y_train,
)
class_weight = {
    int(cls): float(weight)
    for cls, weight in zip(unique_classes, weights)
}

print("class_weight:", class_weight)

# ============================================================
# LSTM + 정적정보 MLP 모델
# ============================================================
sensor_input = Input(
    shape=(SEQUENCE_LENGTH, len(SENSOR_CHANNELS)),
    name="sensor_sequence",
)

x = LSTM(64, return_sequences=True)(sensor_input)
x = Dropout(0.20)(x)
x = LSTM(32)(x)
x = Dense(32, activation="relu")(x)

static_input = Input(
    shape=(X_static_train.shape[1],),
    name="static_input",
)

s = Dense(128, activation="relu")(static_input)
s = Dropout(0.20)(s)
s = Dense(64, activation="relu")(s)

z = Concatenate()([x, s])
z = Dense(64, activation="relu")(z)
z = Dropout(0.30)(z)
z = Dense(32, activation="relu")(z)

output = Dense(
    len(label_encoder.classes_),
    activation="softmax",
    name="damage_grade",
)(z)

model = Model(
    inputs={
        "sensor_sequence": sensor_input,
        "static_input": static_input,
    },
    outputs=output,
)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

model.summary()

callbacks = [
    EarlyStopping(
        monitor="val_loss",
        patience=5,
        restore_best_weights=True,
    ),
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=2,
        min_lr=1e-5,
        verbose=1,
    ),
]

# ============================================================
# 학습
# ============================================================
model.fit(
    {
        "sensor_sequence": X_seq_train,
        "static_input": X_static_train,
    },
    y_train,
    validation_data=(
        {
            "sensor_sequence": X_seq_val,
            "static_input": X_static_val,
        },
        y_val,
    ),
    epochs=30,
    batch_size=256,
    class_weight=class_weight,
    callbacks=callbacks,
    verbose=1,
)

# ============================================================
# 테스트 평가
# ============================================================
probs = model.predict(
    {
        "sensor_sequence": X_seq_test,
        "static_input": X_static_test,
    },
    verbose=0,
)

pred = np.argmax(probs, axis=1)

print("\nAccuracy:", accuracy_score(y_test, pred))
print("Balanced Accuracy:", balanced_accuracy_score(y_test, pred))
print("Macro F1:", f1_score(y_test, pred, average="macro"))
print()
print(
    classification_report(
        y_test,
        pred,
        target_names=[str(x) for x in label_encoder.classes_],
        digits=4,
    )
)

# ============================================================
# 저장
# ============================================================
model.save(MODEL_PATH)

joblib.dump(
    {
        "static_preprocessor": static_preprocessor,
        "sensor_scaler": sensor_scaler,
        "label_encoder": label_encoder,
        "static_features": STATIC_FEATURES,
        "categorical_features": categorical_features,
        "numeric_features": numeric_features,
        "sensor_features": SENSOR_FEATURES,
        "sensor_channels": SENSOR_CHANNELS,
        "sequence_length": SEQUENCE_LENGTH,
    },
    PREPROCESS_PATH,
)

print("\n저장 완료")
print("모델:", MODEL_PATH)
print("전처리 정보:", PREPROCESS_PATH)
