"""Full-page screenshots of the store app for the writeup, signed in as one store's manager.

Needs the app running (uv run python manage.py runserver) with DJANGO_DEMO_SIGN_IN=True.

    uv run python scripts/take_screenshots.py
    uv run python scripts/take_screenshots.py --store PC-0012 --only home sales
    uv run python scripts/take_screenshots.py --base https://<store app> --out docs/screenshots/production/app --only home assistant
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs' / 'screenshots' / 'app'

# (file name, path, what to wait for or do first)
SHOTS = [
    ('01-home', '/', None),
    ('02-sales-overview', '/sales/', None),
    ('03-sales-new', '/sales/?tab=new&find=litter', None),
    ('04-sales-details', '/sales/?tab=details&q=Miller', 'pick'),
    ('05-sales-return', '/sales/?tab=return&q=Miller', 'pick'),
    ('06-customers', '/customers/', None),
    ('07-customers-update', '/customers/?tab=update&q=Smith', 'pick'),
    ('08-animals', '/animals/', None),
    ('09-animals-receive', '/animals/?tab=create', None),
    ('10-employees', '/employees/', None),
    ('11-caretakers', '/caretakers/', None),
    ('12-products', '/products/?show=reorder', None),
    ('12b-animals-over-45-days', '/animals/?status=long', None),
    ('13-categories', '/categories/?size=50', None),
    ('14-policies', '/policies/', None),
    ('15-policy-returns', '/policies/returns-and-refunds/', None),
    ('16-policy-state', '/policies/pacific-northwest-scheduling/', None),
    ('17-demo-sign-in', '/accounts/demo/', 'signed-out'),
    ('18-assistant', '/assistant/', None),
    # Real questions to the Store Assistant (needs ANTHROPIC_API_KEY), with the steps it took opened.
    ('19-assistant-animals', '/assistant/',
     ('ask', 'Which animals have been here longest without selling, and who is looking after them?')),
    ('20-assistant-revenue', '/assistant/',
     ('ask', 'How did revenue last quarter compare with the same quarter last year, by department?')),
    # Policy search answers with cited sections; it needs pgvector, so it only works in production.
    ('21-assistant-policy', '/assistant/',
     ('ask', 'A customer bought a hamster here nine days ago and it is sick. What does our policy say we can offer, '
             'and how many live animals have been returned at this store this year?')),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--store', default='PC-0012', help='The store code to sign in as.')
    parser.add_argument('--only', nargs='*', help='Only shots whose names contain one of these words.')
    parser.add_argument('--out', type=Path, default=OUT, help='Where to save them.')
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        signed_out = browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=2, color_scheme='light')
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=2, color_scheme='light')
        for tab in (signed_out, page):
            tab.set_default_timeout(180_000)  # A store's first page in production reads its data from disk.
        # Pick the store from the list under the map, then sign in on the prefilled form.
        page.goto(f'{args.base}/accounts/demo/')
        page.locator('button.linkbutton', has_text=args.store).click()
        page.wait_for_url('**/accounts/login/**')
        if not args.only or any('login' in word for word in args.only):
            page.screenshot(path=out / '17b-demo-login-prefilled.png', full_page=True)
            print('saved 17b-demo-login-prefilled')
        page.get_by_role('button', name='Sign in').click()
        page.wait_for_url(f'{args.base}/')

        for name, path, action in SHOTS:
            if args.only and not any(word in name for word in args.only):
                continue
            target = signed_out if action == 'signed-out' else page
            target.goto(args.base + path)
            if action == 'signed-out' and 'demo' in name:
                # Wait for the map tiles, then open one store's popup.
                target.wait_for_load_state('networkidle')
                target.wait_for_timeout(1000)
                target.locator('path.leaflet-interactive').nth(40).click()
                target.wait_for_timeout(600)
            if isinstance(action, tuple) and action[0] == 'ask':
                target.fill('textarea[name=question]', action[1])
                target.get_by_role('button', name='Ask').click()
                target.locator('#answer .answer').wait_for(timeout=180_000)
                target.locator('#answer details summary').click()
            if action == 'pick':
                # Open the first match in the record picker.
                target.locator('ul#matches a').first.click()
            target.wait_for_load_state('networkidle')
            target.screenshot(path=out / f'{name}.png', full_page=True)
            print('saved', name)
        browser.close()


if __name__ == '__main__':
    main()
