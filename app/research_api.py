"""Offline research replay API. Does not invoke Gemini or the legacy LSTM."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.research_algorithms import trilaterate

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data/research/processed'
RAW = ROOT / 'data/research/raw'
router = APIRouter(prefix='/api/v1/research', tags=['research'])


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise HTTPException(503, '연구 데이터가 준비되지 않았습니다. fetch_research_data.py와 prepare_research_data.py를 실행하세요.') from error


def find_experiment(experiment_id):
    catalog = read_json(DATA / 'catalog.json')
    if not any(x['id'] == experiment_id for x in catalog['experiments']):
        raise HTTPException(404, '등록되지 않은 실험입니다.')


@router.get('/catalog')
def catalog():
    return read_json(DATA / 'catalog.json')


@router.get('/experiments/{experiment_id}')
def experiment(experiment_id: str):
    find_experiment(experiment_id)
    return read_json(DATA / f'{experiment_id}.json')


@router.get('/experiments/{experiment_id}/csv')
def experiment_csv(experiment_id: str):
    find_experiment(experiment_id)
    path = DATA / f'{experiment_id}.csv'
    if not path.exists(): raise HTTPException(503, 'CSV가 준비되지 않았습니다.')
    return FileResponse(path, filename=path.name, media_type='text/csv; charset=utf-8')


@router.get('/sources/{source_id}')
def source_file(source_id: str):
    sources = read_json(DATA / 'catalog.json')['sources']
    source = next((x for x in sources if x['id'] == source_id), None)
    if source is None: raise HTTPException(404, '등록되지 않은 출처입니다.')
    path = (ROOT / source['path']).resolve()
    if not path.is_relative_to(RAW.resolve()) or not path.is_file():
        raise HTTPException(404, '로컬 원본이 없습니다. 공개 원본 링크를 이용하세요.')
    return FileResponse(path, filename=path.name)


class RangeRequest(BaseModel):
    anchors: list[tuple[float, float]] = Field(min_length=3, max_length=12)
    ranges: list[float] = Field(min_length=3, max_length=12)


@router.post('/uwb')
def uwb(request: RangeRequest):
    try:
        return dict(trilaterate(request.anchors, request.ranges), kind='기하 계산 예제 · 실측 UWB 아님')
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
