"""Rebuild small, inspectable replay files and held-out evaluation from originals.

Run from the project root: python scripts/prepare_research_data.py
Original observations are not fabricated or rescaled to achieve desired results.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import py7zr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.research_algorithms import flashover_proxy, pdr, structural_anomaly, structural_limits

RAW = ROOT / 'data/research/raw'
OUT = ROOT / 'data/research/processed'


def clean(value):
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)): return [clean(v) for v in value]
    if isinstance(value, (np.floating, float)): return round(float(value), 5) if np.isfinite(value) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.bool_): return bool(value)
    return value


def save(experiment):
    result = clean(experiment)
    (OUT / f"{result['id']}.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    with (OUT / f"{result['id']}.csv").open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result['points'][0]))
        writer.writeheader(); writer.writerows(result['points'])
    return {k: v for k, v in result.items() if k != 'points'}


def score_forecasts(t, temp, forecast):
    # Evaluate before the FIRST crossing only, where a full future horizon exists.
    crossings = np.flatnonzero(temp >= 600)
    event = float(t[crossings[0]]) if len(crossings) else None
    counts = {method: dict(tp=0, fp=0, fn=0, tn=0) for method in ['trend', 'temperature_400']}
    lead = None
    eligible = 0
    for i, at in enumerate(t):
        if at + 60 > t[-1] or (event is not None and at >= event) or not np.isfinite(forecast[i]): continue
        future = temp[(t > at) & (t <= at + 60)]
        if not len(future) or not np.isfinite(future).all(): continue
        actual = bool(np.any(future >= 600)); eligible += 1
        for name, pred in [('trend', forecast[i] >= 600), ('temperature_400', temp[i] >= 400)]:
            counts[name]['tp' if pred and actual else 'fp' if pred else 'fn' if actual else 'tn'] += 1
        if event is not None and actual and forecast[i] >= 600 and lead is None:
            lead = event - at
    return dict(first_600_s=event, eligible_windows=eligible, lead_s=lead, confusion=counts)


def prepare_fire():
    metadata = []
    for n in range(1, 5):
        d = pd.read_csv(RAW / f'UL_NIST_Vents_Test_{n}.csv')
        t = pd.to_numeric(d.Time).to_numpy(float)
        temp = pd.to_numeric(d.T_upper, errors='coerce').to_numpy(float)
        result = flashover_proxy(t, temp)
        metadata.append(save(dict(
            id=f'flash-{n}', module='flashover', title=f'UL/NIST 화재 실험 {n}',
            split='개발 확인' if n == 1 else '분리 평가', source_ids=[f'flashover_{n}'],
            kind='실제 가스버너 화재 실험 · 열전대 기반 고온층 추정값', duration_s=float(t[-1]),
            description='2012년 UL/NIST 환기 실험. 자연가스 버너와 천장 환기구를 조절한 별도 실험이며 실제 플래시오버 정답은 제공되지 않습니다.',
            channels='Time [s], T_upper [°C]. 원본 누락 17개(Test 1)는 보간하지 않음.',
            thresholds=dict(temperature_c=600, window_s=60, horizon_s=60, baseline_c=400),
            metrics=dict(score_forecasts(t, temp, result['predicted_c']), peak_c=float(np.nanmax(temp)), missing=int(np.isnan(temp).sum())),
            points=[dict(t=t[i], temperature_c=temp[i], slope_c_min=result['slope_c_s'][i]*60,
                         predicted_c=result['predicted_c'][i], state=result['state'][i]) for i in range(len(t))])))
    return metadata


def prepare_structure():
    workbook = openpyxl.load_workbook(RAW / 'steel_beam.xlsx', read_only=True, data_only=True)
    arrays = {}
    for n in [7, 8, 9]:
        rows = list(workbook[f'Test{n}'].values)
        headers = [''.join(str(v).split()).lower() for v in rows[0]]
        indices = [headers.index(c) for c in ['testtime(s)', 'vd1(mm)', 'tc17(degc)']]
        a = np.array([[r[j] for j in indices] for r in rows[1:]], dtype=float)
        arrays[n] = a[np.isfinite(a[:, 0])]  # Exclude only empty trailing worksheet rows.
    workbook.close()
    limits = structural_limits(arrays[7][:, 0], arrays[7][:, 1])
    metadata = []
    for n, a in arrays.items():
        t, d, temperature = a.T
        result = structural_anomaly(t, d, limits)
        alarm = [i for i, s in enumerate(result['state']) if s == 'anomaly']
        metadata.append(save(dict(
            id=f'beam-{n}', module='collapse', title=f'NIST 강재 보 Test {n}',
            split='초기 60초 기준 보정' if n == 7 else '분리 적용', source_ids=['collapse'],
            kind='실제 가열·하중 재하 실험', duration_s=float(t[-1]),
            description='6.2 m W16×26 강재 보의 변형 신호. 건물 전체 붕괴 확률이나 붕괴 시각을 예측한 결과가 아닙니다.',
            channels='Test Time [s], VD1 수직 변위 [mm], tc17 보 온도 [°C]. tc17은 기체 온도가 아닙니다.',
            thresholds=limits,
            metrics=dict(first_anomaly_s=t[alarm[0]] if alarm else None,
                         max_displacement_mm=float(np.nanmax(np.abs(result['displacement_mm']))),
                         max_rate_mm_min=float(np.nanmax(np.abs(result['rate_mm_min']))),
                         accuracy=None, limitation='붕괴 정답 시점/비붕괴 대조군이 없어 정확도·리드타임은 계산하지 않음'),
            points=[dict(t=t[i], displacement_mm=result['displacement_mm'][i], temperature_c=temperature[i],
                         rate_mm_min=result['rate_mm_min'][i], state=result['state'][i]) for i in range(len(t))])))
    return metadata


def read_sensor(path):
    d = pd.read_csv(path)
    d['at'] = d.tow.astype(float) + d.nano.astype(float) * 1e-9
    return d.sort_values('at').drop_duplicates('at')


def prepare_position():
    directory = RAW / 'walking'
    if not (directory / 'S1/TEST_02').exists() or not (directory / 'S2/TEST_04').exists():
        with py7zr.SevenZipFile(RAW / 'walking.7z') as z: z.extractall(directory)
        for subject in ['S1', 'S2']:
            with py7zr.SevenZipFile(directory / 'Geoloc_ds022023' / f'{subject}.7z') as z: z.extractall(directory)
    tracks = {}
    for n in [2, 3, 4]:
        folder = directory / ('S1' if n < 4 else 'S2') / f'TEST_{n:02d}'
        acceleration = read_sensor(folder / 'raw_measurement/acceleration.csv')
        gyro = read_sensor(folder / 'raw_measurement/rotation.csv')
        # As-of alignment takes the most recent gyro value; never a future sample.
        joined = pd.merge_asof(acceleration, gyro[['at', 'z']].rename(columns={'z': 'gyro_z'}), on='at', direction='backward', tolerance=.03)
        if joined.gyro_z.isna().any(): raise ValueError(f'Unmatched gyroscope in TEST_{n}')
        t = joined['at'].to_numpy()
        gt = pd.read_csv(folder / 'ground_truth/gt_trajectory.csv').sort_values('tow').drop_duplicates('tow')
        result = pdr(t, joined[['x', 'y', 'z']].to_numpy(), joined.gyro_z.to_numpy(), step_length=1.)
        tracks[n] = (t, result, gt)
    # Only development TEST_02 supplies step length. Low-rate reference distance avoids high-rate jitter.
    t, result, gt = tracks[2]
    sample = np.arange(max(gt.tow.iloc[0], t[0]+40), min(t[-1], gt.tow.iloc[-1]), 1.)
    ref = np.column_stack([np.interp(sample, gt.tow, gt[k]) for k in ['pos_x', 'pos_y']])
    count = np.count_nonzero((t[result['steps']] >= sample[0]) & (t[result['steps']] <= sample[-1]))
    step_length = float(np.linalg.norm(np.diff(ref, axis=0), axis=1).sum() / count)
    if not .2 < step_length < 1.5: raise ValueError('Implausible calibrated step length')
    metadata = []
    for n, (t, result, gt) in tracks.items():
        xy = result['xy'] * step_length
        start = float(max(gt.tow.iloc[0], t[0]+40))
        ready = start + 10
        i0, i1 = np.searchsorted(t, [start, ready], side='right') - 1
        # This initial reference segment is explicitly disclosed and excluded from evaluation.
        ref0 = np.array([np.interp(t[i0], gt.tow, gt[k]) for k in ['pos_x', 'pos_y']])
        ref1 = np.array([np.interp(t[i1], gt.tow, gt[k]) for k in ['pos_x', 'pos_y']])
        v, r = xy[i1] - xy[i0], ref1 - ref0
        angle = np.arctan2(r[1], r[0]) - np.arctan2(v[1], v[0])
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        xy = (xy - xy[i0]) @ rotation.T + ref0
        query = np.arange(start, min(t[-1], gt.tow.iloc[-1]), .5)
        idx = np.searchsorted(t, query, side='right') - 1
        at = t[idx]
        truth = np.column_stack([np.interp(at, gt.tow, gt[k]) for k in ['pos_x', 'pos_y']])
        errors = np.linalg.norm(xy[idx] - truth, axis=1)
        valid = at >= ready
        steps = np.searchsorted(result['steps'], idx, side='right')
        metadata.append(save(dict(
            id=f'walk-{n}', module='position', title=f'ULISS 보행 TEST {n:02d}',
            split='보폭 보정 · 참가자 1' if n == 2 else f'분리 평가 · 참가자 {1 if n == 3 else 2}', source_ids=['position'],
            kind='실제 휴대형 IMU · 발 부착 INS 기준 추정궤적', duration_s=float(at[-1]-start),
            description='평평하게 든 센서의 자연 보행. TEST 03은 사무실·계단 포함, TEST 04는 야외 숲길. 소방대원 포복·장비 착용 데이터가 아닙니다.',
            channels='가속도 [m/s²], 회전 [rad/s], GPS tow+nano [s]. 자기장 단위·보정치 매칭 불명확으로 자력계는 사용하지 않음.',
            thresholds=dict(step_length_m=step_length, peak_m_s2=1., refractory_s=.28, gyro_bias=result['gyro_bias'], heading_calibration_s=10),
            metrics=dict(mean_error_m=float(errors[valid].mean()), p95_error_m=float(np.quantile(errors[valid], .95)),
                         end_error_m=float(errors[-1]), evaluation_points=int(valid.sum()), steps=int(steps[-1]),
                         limitation='첫 40초 정지 보정 + 초기 10초 기준 방향 보정. 이후 기준 궤적은 오차 계산에만 사용. 기준도 INS 추정값이며 실내 소방 성능으로 일반화 불가.'),
            points=[dict(t=at[j]-start, north_m=xy[idx[j], 0] if valid[j] else None,
                         east_m=xy[idx[j], 1] if valid[j] else None, ref_north_m=truth[j, 0], ref_east_m=truth[j, 1],
                         error_m=errors[j] if valid[j] else None, steps=steps[j],
                         state='estimated' if valid[j] else 'unknown') for j in range(len(at))])))
    return metadata


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads((RAW.parent / 'sources.json').read_text(encoding='utf-8'))
    for source in sources:
        if hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError(f"Source has changed: {source['path']}")
    experiments = prepare_fire() + prepare_structure() + prepare_position()
    catalog = dict(version=1, experiments=experiments, sources=sources,
                   attribution='원본: NIST / firemodels; Fu, Hanyuan · Université Gustave Eiffel / Recherche Data Gouv. 2026-10-03: 선택 채널 추출, 알고리즘 결과 및 검증 지표를 추가한 파생 자료.',
                   independent_streams=True)
    (OUT / 'catalog.json').write_text(json.dumps(clean(catalog), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    for item in experiments: print(item['id'], item['metrics'])


if __name__ == '__main__': main()
