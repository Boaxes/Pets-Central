"""Screenshots of the Dagster UI for the writeup, in the light theme at high resolution. Needs `dagster dev` running.

Lineage comes from Dagster's own "Download as SVG". Those SVGs draw their labels with Dagster's font, so each is also
rendered to a PNG inside a Dagster page, where that font is loaded; elsewhere the labels get cut short.

    uv run --project orchestration python scripts/take_dagster_screenshots.py --run <run id>
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

LOCATION = 'orchestration.definitions'
SCREENS = [
    ('01-runs', '/runs'),
    ('02-run-timeline', '/runs/{run}'),
    ('03-schedule', f'/locations/{LOCATION}/schedules/daily_pipeline_schedule'),
    ('04-raw-table', '/assets/store_ops/sales'),
    ('05-mart-checks', '/assets/marts/fct_sales?view=checks'),
]
LINEAGE = [
    ('lineage-groups', '/asset-groups'),
    ('lineage-fct-sales', '/assets/marts/fct_sales?view=lineage&lineageScope=upstream&lineageDepth=3'),
    ('lineage-dim-customers', '/assets/marts/dim_customers?view=lineage&lineageScope=upstream&lineageDepth=4'),
]


def open_page(page, url):
    page.goto(url)
    try:
        page.wait_for_load_state('networkidle', timeout=15_000)
    except TimeoutError:
        pass  # A busy instance keeps polling, so the network may never go quiet; the wait below covers it.
    page.wait_for_timeout(5000)  # Graphs and timelines lay themselves out after loading.
    skip = page.get_by_role('button', name='Skip')  # Dagster's "join the community" prompt.
    if skip.is_visible():
        skip.click()
        page.wait_for_timeout(500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:3000')
    parser.add_argument('--run', required=True, help='The run to show in the timeline.')
    parser.add_argument('--out', default='docs/screenshots/dagster-local')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, device_scale_factor=2,
                                      color_scheme='light', accept_downloads=True)
        page = context.new_page()
        for name, path in SCREENS:
            open_page(page, args.base + path.format(run=args.run))
            page.screenshot(path=out / f'{name}.png')
            print('saved', name)

        for name, path in LINEAGE:
            open_page(page, args.base + path)
            with page.expect_download() as download:
                page.locator('[aria-label=download_for_offline]').first.click()
            download.value.save_as(out / f'{name}.svg')
            print('saved', f'{name}.svg')

        for name, _ in LINEAGE:
            svg = (out / f'{name}.svg').read_text(encoding='utf-8')
            width, height = (float(x) for x in re.search(r'<svg[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"',
                                                         svg).groups())
            render = browser.new_page(viewport={'width': int(width) + 40, 'height': int(height) + 40},
                                      device_scale_factor=3, color_scheme='light')
            render.goto(args.base + '/runs')
            render.wait_for_load_state('load')
            render.wait_for_timeout(3000)
            render.evaluate("""svg => { document.body.innerHTML =
                '<div id="lineage" style="position:fixed;inset:0;background:#fff;padding:20px">' + svg + '</div>'; }""",
                            svg)
            render.evaluate('document.fonts.ready')
            render.wait_for_timeout(1500)
            render.locator('#lineage').screenshot(path=out / f'{name}.png', timeout=120_000)
            render.close()
            print('saved', f'{name}.png')
        browser.close()


if __name__ == '__main__':
    main()
