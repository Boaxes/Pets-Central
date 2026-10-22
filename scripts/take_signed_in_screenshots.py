"""Screenshots of the Azure portal, GitHub and Snowflake, from the profile scripts/signed_in_browser.py signed in.

    uv run python scripts/take_signed_in_screenshots.py              # every shot
    uv run python scripts/take_signed_in_screenshots.py azure/02     # only shots whose path starts with this

Shots land in docs/screenshots/production/<site>/, 3840x2160 (1920x1080 at 2x), light theme.
"""

import base64
import gzip
import re
import sys
from pathlib import Path

from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signed_in_browser import open_profile  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / 'docs' / 'screenshots' / 'production'
SUB = '/subscriptions/022e5b87-f788-4401-a79a-24e86976ea0b'
PROD = f'https://portal.azure.com/#@/resource{SUB}/resourceGroups/rg-pets-central-prod'
VENDOR = f'https://portal.azure.com/#@/resource{SUB}/resourceGroups/rg-pets-central-vendor'
REPO = 'https://github.com/Boaxes/pets-central'
SNOWFLAKE = 'https://app.snowflake.com/zdnloqp/zb02546/#'

SNOWFLAKE_TREE = ('Find objects by name', 'PETS_CENTRAL')
ANALYTICS = f'{SNOWFLAKE}/streamlit-apps/PETS_CENTRAL.APPS.PETS_ANALYTICS'
PG = f'{PROD}/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-pets-central-022e5b87'

# Every pipeline run's start and finish, from the Dagster daemon's logs. The portal opens a shared query link with the
# query gzipped and base64-encoded.
RUN_LOG_QUERY = r'''ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-pets-dagster" and Log_s has_any ("RUN_START", "RUN_SUCCESS", "RUN_FAILURE")
| extend Run = extract(@"daily_pipeline - (\w{8})", 1, Log_s), Event = extract(@"(RUN_\w+)", 1, Log_s)
| project TimeGenerated, Run, Event
| order by TimeGenerated asc'''
WORKSPACE = f'{SUB}/resourceGroups/rg-pets-central-prod/providers/Microsoft.OperationalInsights/workspaces/log-pets-central'
RUN_LOGS = ('https://portal.azure.com/#@/blade/Microsoft_OperationsManagementSuite_Workspace/Logs.ReactView/resourceId/'
            f'{quote(WORKSPACE, safe="")}/source/LogsBlade.AnalyticsShareLinkToQuery/q/'
            f'{quote(base64.b64encode(gzip.compress(RUN_LOG_QUERY.encode())).decode(), safe="")}/timespan/P2D')

# (path, url, and optionally a dict of steps before the shot:
#   filter: (placeholder of a search box, text to type in it), so only this project's things are listed
#   pick:   [(role, name), ...] to click in order, such as a filter menu and one of its options; skipped if absent
#   then:   more clicks after the filter is filled in; wait: seconds to wait at the end (an answer being written)
#   scroll: a heading to scroll to the top; end_at: text to scroll to the bottom of the shot;
#   bottom: scroll every frame's scrolling areas, except a Streamlit sidebar, to their end)
SHOTS = [
    ('azure/01-resource-groups', 'https://portal.azure.com/#browse/resourcegroups', {'filter': ('Filter', 'pets-central')}),
    ('azure/02-production-resources', f'{PROD}/overview'),
    ('azure/03-store-app', f'{PROD}/providers/Microsoft.App/containerApps/ca-pets-store/appOverview'),
    ('azure/04-store-revisions', f'{PROD}/providers/Microsoft.App/containerApps/ca-pets-store/revisionManagement'),
    ('azure/05-dagster-containers', f'{PROD}/providers/Microsoft.App/containerApps/ca-pets-dagster/containers'),
    ('azure/06-manage-job-runs', f'{PROD}/providers/Microsoft.App/jobs/caj-pets-manage/executionHistory'),
    ('azure/07-postgres', f'{PG}/overview'),
    ('azure/08-postgres-databases', f'{PG}/databases'),
    ('azure/09-postgres-pgvector', f'{PG}/serverParameters', {'filter': ('Search to filter', 'azure.extensions')}),
    ('azure/10-key-vault-secrets', f'{PROD}/providers/Microsoft.KeyVault/vaults/kv-pets-022e5b87/secrets'),
    ('azure/11-openai-embeddings', f'{PROD}/providers/Microsoft.CognitiveServices/accounts/oai-pets-022e5b87/overview'),
    ('azure/12-rewards-api', f'{VENDOR}/providers/Microsoft.Web/sites/func-pets-rewards-022e5b87/appServices'),
    ('azure/13-budget', f'https://portal.azure.com/#@/resource{SUB}/budgets'),
    # Closes the Queries hub that covers the results, and switches the editor to KQL so the query shows.
    ('azure/14-dagster-run-logs', RUN_LOGS,
     {'pick': [('button', re.compile('^Close$')), ('combobox', 'Choose working mode'), ('option', 'KQL mode')]}),
    # After the shutdown: production's resource group, empty.
    ('azure/15-production-destroyed', f'{PROD}/overview'),
    ('github/02-ci-run', f'{REPO}/actions/runs/39242382124'),
    ('github/03-ci-terraform-plan', f'{REPO}/actions/runs/39242382124', {'scroll': 'Terraform plan summary'}),
    ('github/04-deploy-run', f'{REPO}/actions/runs/39242898577'),
    ('github/05-actions', f'{REPO}/actions'),
    ('github/06-destroy-run', f'{REPO}/actions/runs/39298932154', {'end_at': 'Destroy complete!'}),
    # The catalog tree and the warehouse's user list also hold another project's database and user, so both are
    # narrowed to this project's.
    ('snowflake/01-database', f'{SNOWFLAKE}/data/databases/PETS_CENTRAL', {'filter': SNOWFLAKE_TREE}),
    ('snowflake/02-raw-tables', f'{SNOWFLAKE}/data/databases/PETS_CENTRAL/schemas/RAW', {'filter': SNOWFLAKE_TREE}),
    ('snowflake/03-mart-tables', f'{SNOWFLAKE}/data/databases/PETS_CENTRAL/schemas/MARTS', {'filter': SNOWFLAKE_TREE}),
    ('snowflake/04-dbt-queries', f'{SNOWFLAKE}/compute/warehouses/PETS_WH',
     {'pick': [('button', 'bulldogpancake2'), ('option', 'PETS_DBT_SVC')]}),
    ('snowflake/05-loader-queries', f'{SNOWFLAKE}/compute/warehouses/PETS_WH',
     {'pick': [('button', 'bulldogpancake2'), ('option', 'PETS_LOADER_SVC')]}),
    ('snowflake/06-resource-monitor', f'{SNOWFLAKE}/compute/resource-monitors'),
    # The analytics app, in Streamlit in Snowflake. Its pages are links in the app's own sidebar.
    ('snowflake/07-analytics-overview', ANALYTICS),
    ('snowflake/08-analytics-sales', ANALYTICS, {'pick': [('link', 'Sales')], 'wait': 20}),
    ('snowflake/09-analytics-customers', ANALYTICS, {'pick': [('link', 'Customers and Loyalty')], 'wait': 20}),
    ('snowflake/10-analytics-campaigns', ANALYTICS, {'pick': [('link', 'Campaigns')], 'wait': 20}),
    ('snowflake/11-analytics-ask', ANALYTICS,
     {'pick': [('link', 'Ask')], 'filter': ('Which region', 'Which department had the highest gross margin rate in 2025?'),
      'then': [('key', 'Enter'), ('button', re.compile('^Ask$'))], 'wait': 60}),
    ('snowflake/12-analytics-ask-result', ANALYTICS,
     {'pick': [('link', 'Ask')], 'filter': ('Which region', 'Which department had the highest gross margin rate in 2025?'),
      'then': [('key', 'Enter'), ('button', re.compile('^Ask$'))], 'wait': 60, 'bottom': True}),
]

# Account-wide notices on GitHub (a 2FA reminder, platform announcements) that say nothing about this project.
GITHUB_NOTICES = 'x-banner, section[class*="prc-Banner-Banner"] { display: none !important; }'


def click(page, steps):
    """Clicks each (role, name) in turn, in whichever frame shows it; one that isn't there is skipped. A ('key',
    name) step presses that key instead."""
    for role, label in steps:
        if role == 'key':
            page.keyboard.press(label)
            page.wait_for_timeout(2000)
            continue
        found = [loc for f in page.frames for loc in f.get_by_role(role, name=label).all() if loc.is_visible()]
        if found:
            try:
                found[0].click(timeout=5000)
            except PlaywrightTimeout:  # covered, such as by a portal notification
                found[0].evaluate('e => e.click()')
            page.wait_for_timeout(4000)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ''
    with sync_playwright() as p:
        browser = open_profile(p, headless=True)
        for name, url, *options in SHOTS:
            options = options[0] if options else {}
            if not name.startswith(only):
                continue
            page = browser.new_page()  # a fresh tab each time: the portal tabs grow until they crash
            page.goto(url, wait_until='domcontentloaded', timeout=90000)
            # The log query has to run, and the analytics app's container has to start.
            page.wait_for_timeout(90000 if url == ANALYTICS else 30000 if url == RUN_LOGS else 15000)
            snowflake = url.startswith(SNOWFLAKE)
            if snowflake and page.get_by_role('button', name='Ok', exact=True).count():
                page.get_by_role('button', name='Ok', exact=True).first.click()  # a "CoCo is here" announcement
            click(page, options.get('pick', []))
            if 'filter' in options:
                placeholder, text = options['filter']
                # The portal draws some blades inside iframes, so look for the box in every frame.
                boxes = [f.get_by_placeholder(placeholder) for f in page.frames]
                next(b for b in boxes if b.count()).first.fill(text)
                page.wait_for_timeout(4000)
                if options['filter'] == SNOWFLAKE_TREE:
                    page.keyboard.press('Escape')  # closes the "Ask CoCo about ..." suggestion under the box
            click(page, options.get('then', []))
            page.wait_for_timeout(options.get('wait', 0) * 1000)
            if url.startswith('https://github.com'):
                page.add_style_tag(content=GITHUB_NOTICES)
            if 'scroll' in options:
                page.get_by_role('heading', name=options['scroll']).evaluate('e => e.scrollIntoView()')
                page.wait_for_timeout(1000)
            if 'end_at' in options:
                page.get_by_text(options['end_at']).first.evaluate('e => e.scrollIntoView({block: "end"})')
                page.wait_for_timeout(1000)
            if options.get('bottom'):
                for f in page.frames:
                    f.evaluate('() => document.querySelectorAll("*").forEach(e => {'
                               ' if (e.scrollHeight > e.clientHeight + 10 && !e.closest("[data-testid=stSidebar]"))'
                               ' e.scrollTop = e.scrollHeight; })')
                page.wait_for_timeout(2000)
            path = OUT / f'{name}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=path)
            print(path.relative_to(OUT), page.title()[:70])
            page.close()
        browser.close()


if __name__ == '__main__':
    main()
