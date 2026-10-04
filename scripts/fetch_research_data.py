"""Download the selected public research files, preserving provenance and hashes."""
from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'research' / 'raw'
REVISION = 'ae8a6fca191222d2c047903bdcf61fb49bfb3f41'
BASE = f'https://raw.githubusercontent.com/firemodels/exp/{REVISION}'
SOURCES = [
    dict(id='collapse', filename='steel_beam.xlsx', url='https://s3.amazonaws.com/nist-midas/1856/NFRL_LocalizedFireTest_SteelBeam_09012017.xlsx',
         landing='https://doi.org/10.18434/mds2-1856', license='https://www.nist.gov/open/license', kind='실제 강재 보 실험'),
    dict(id='position', filename='walking_bundle.zip', url='https://entrepot.recherche.data.gouv.fr/api/access/datafiles/163262,163263',
         landing='https://doi.org/10.57745/ZCBIIB', license='https://spdx.org/licenses/etalab-2.0.html', kind='실제 보행 센서'),
    dict(id='fire_license', filename='firemodels_LICENSE.txt', url=f'{BASE}/LICENSE.md',
         landing='https://github.com/firemodels/exp', license=f'{BASE}/LICENSE.md', kind='원본 이용 고지'),
]
SOURCES += [dict(id=f'flashover_{n}', filename=f'UL_NIST_Vents_Test_{n}.csv',
                url=f'{BASE}/UL_NIST_Vents/UL_NIST_Vents_Test_{n}.csv',
                landing=f'https://github.com/firemodels/exp/tree/{REVISION}/UL_NIST_Vents',
                license=f'{BASE}/LICENSE.md', kind='실제 화재 실험에서 산출한 고온층 온도', revision=REVISION)
            for n in range(1, 5)]


def download(source):
    target = RAW / source['filename']
    if not target.exists():
        print('Downloading', source['filename'], flush=True)
        request = urllib.request.Request(source['url'], headers={'User-Agent': 'FireSafetyStudentResearch/1.0'})
        with urllib.request.urlopen(request, timeout=90) as response:
            temporary = target.with_suffix(target.suffix + '.part')
            with temporary.open('wb') as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            temporary.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if source.get('sha256') and digest != source['sha256']:
        raise ValueError(f'Checksum mismatch: {target.name}')
    record = dict(source, sha256=digest, bytes=target.stat().st_size,
                  retrieved_at=datetime.now(timezone.utc).isoformat(), path=target.relative_to(ROOT).as_posix())
    print('Verified', target.name, record['bytes'], flush=True)
    return record


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(download, SOURCES))
    with zipfile.ZipFile(RAW / 'walking_bundle.zip') as archive:
        for name, filename, expected in [
            ('Geoloc_ds022023.7z', 'walking.7z', '58f6ec6c40cc9feaf3b43d8bdea14184'),
            ('README_Dataset-EN.txt', 'walking_readme.txt', '63813a767eae73ba1a463d4ce5be44d6')]:
            payload = archive.read(name)
            if hashlib.md5(payload).hexdigest() != expected:
                raise ValueError(f'Publisher checksum mismatch: {name}')
            (RAW / filename).write_bytes(payload)
            records.append(dict(id=filename, path=f'data/research/raw/{filename}',
                                sha256=hashlib.sha256(payload).hexdigest(), publisher_md5=expected,
                                bytes=len(payload), container='walking_bundle.zip'))
    (RAW.parent / 'sources.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
