"""A browser profile for screenshots of sites that need a sign-in: the Azure portal, GitHub and Snowflake.

    uv run python scripts/signed_in_browser.py            # opens a window: sign in to each tab, then close it
    uv run python scripts/signed_in_browser.py --check    # reports which sites the profile is signed in to

The profile lives in data/browser_profile (git-ignored), so the sign-ins stay on this machine. The owner signs in;
the screenshot scripts only reuse the profile.
"""

import argparse
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = Path(__file__).resolve().parent.parent / 'data' / 'browser_profile'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SITES = {
    'Azure portal': 'https://portal.azure.com/',
    'GitHub': 'https://github.com/login',
    # The account's own sign-in page, which offers the account's sign-in options (Google, for this one).
    'Snowflake': 'https://app.snowflake.com/zdnloqp/zb02546/',
}


def open_profile(playwright, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    # The installed Google Chrome, with this separate profile; the owner's own Chrome profile isn't touched.
    return playwright.chromium.launch_persistent_context(
        PROFILE, channel='chrome', headless=headless, viewport={'width': 1920, 'height': 1080},
        device_scale_factor=2, color_scheme='light')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        with sync_playwright() as p:
            browser = open_profile(p, headless=True)
            page = browser.new_page()
            for name, url in SITES.items():
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_timeout(6000)
                signed_in = 'login' not in page.url and 'signin' not in page.url.lower() and 'oauth2' not in page.url
                print(f'{name}: {"signed in" if signed_in else "not signed in"} ({page.url[:60]})')
            browser.close()
            return
    # Signing in happens in plain Chrome, not one Playwright controls: Google refuses sign-ins from automated browsers.
    print('Sign in to each tab, then close the window.')
    subprocess.run([CHROME, f'--user-data-dir={PROFILE}', '--no-first-run', *SITES.values()])


if __name__ == '__main__':
    main()
