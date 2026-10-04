"""Optional real-browser smoke check: pip install playwright; uses installed Edge."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/research-ui'
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000/research')
    page.wait_for_function("document.querySelector('#workspace').getAttribute('aria-busy') === 'false' && document.querySelector('#experiment').value === 'flash-4'")
    assert page.locator('#load-error').is_hidden()
    page.get_by_role('button', name='주요 구간으로 이동').click()
    before = page.locator('#timeline').input_value()
    page.locator('#speed').select_option('60')
    page.get_by_role('button', name='실험 재생', exact=True).click()
    page.wait_for_timeout(1200)
    page.get_by_role('button', name='실험 일시정지', exact=True).click()
    assert int(page.locator('#timeline').input_value()) > int(before)
    assert '600°C 기준 도달' in page.locator('#status-text').inner_text()
    page.screenshot(path=str(OUT/'desktop-flash.png'), full_page=True)
    with page.expect_download() as download:
        page.get_by_role('link', name='분석 CSV').click()
    download.value.save_as(str(OUT/'download.csv'))
    assert 'temperature_c' in (OUT/'download.csv').read_text(encoding='utf-8-sig')
    page.locator('[data-module="collapse"]').click()
    page.wait_for_function("document.querySelector('#plot-title').textContent === '구조 변위의 변화'")
    page.locator('#experiment').select_option('beam-8')
    page.wait_for_function("document.querySelector('#metrics').textContent.includes('미감지')")
    page.get_by_role('button', name='주요 구간으로 이동').click()
    assert page.locator('#status-text').inner_text() != '변형 이상 감지'
    page.locator('[data-module="position"]').click()
    page.wait_for_function("document.querySelector('#plot-title').textContent === '보행 궤적과 누적 오차'")
    page.get_by_role('button', name='주요 구간으로 이동').click()
    page.locator('#timeline').focus()
    old = int(page.locator('#timeline').input_value())
    page.keyboard.press('ArrowRight')
    assert int(page.locator('#timeline').input_value()) == old+1
    page.get_by_text('센서 구성과 간단한 프로토타입', exact=True).click()
    page.get_by_role('button', name='위치 계산', exact=True).click()
    page.wait_for_function("document.querySelector('#uwb-result').textContent.includes('(3.00, 4.00)')")
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(OUT/'mobile-position.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    for path in page.locator('#chart path').all():
        assert 'NaN' not in (path.get_attribute('d') or '')
    assert not errors, errors
    print('Browser checks passed: modules, playback, keyboard, CSV, UWB, mobile overflow; no JS errors.')
    browser.close()
