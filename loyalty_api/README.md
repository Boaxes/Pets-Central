# Pawprint Loyalty API

The loyalty and marketing platform's API. In the Pets Central story another company, Pawprint Loyalty, runs the Pets
Central Rewards program on this platform, so it lives in its own folder with its own `pyproject.toml`, and Pets
Central reaches its data only through this API.

It is a FastAPI app hosted in Azure Functions through `func.AsgiFunctionApp`: one function receives every request
and FastAPI routes it. FastAPI gives an automatic `/docs` page and validates every parameter and response.

## What it serves

| Endpoint | What |
|---|---|
| `GET /v2/members` | Loyalty members. No ID in common with store customers. |
| `GET /v2/members/{member_id}` | One member. |
| `GET /v2/campaigns` | Coupon campaigns. |
| `GET /v2/points-transactions` | Points earned, campaign bonuses, reversals and redemptions. |
| `GET /v2/email-events` | Campaign emails sent, opened and clicked. Filter with `campaign_id`. |
| `GET /v2/coupon-redemptions` | Coupon codes used at the register. |
| `GET /v1/members` | The deprecated first version. |
| `GET /health` | No key needed. |

## How it behaves like a real vendor API

- **API key** in the `X-API-Key` header, or 401.
- **Rate limit:** 20 requests per second with bursts of 40, per key. Over the limit is a 429 with `Retry-After`.
- **A public demo key** (`LOYALTY_DEMO_KEY`) for the docs page's Try It Out: 2 requests per second with bursts of 5.
  Only the docs page's origin may call from a browser (the function app's CORS setting, in Terraform).
- **Occasional failures:** about 2% of requests return 503 with `Retry-After: 1` (`LOYALTY_FAILURE_RATE`).
  Clients must retry.
- **Paging:** v2 returns up to 1,000 rows a page, in order of when they changed, with a `next_cursor`. v1 uses
  `page` and `page_size` (up to 100) with a `total`.
- **Two versions:** v1 returns `email_address`, the phone as typed, `name` as "Last, First" and `signup_date` as
  `MM/DD/YYYY HH:MM` in the home store's local time. v2 returns `email`, `phone_e164`, separate names and UTC.
  v1 answers carry `Deprecation` and `Sunset` headers.
- **Mixed time zones:** `occurred_at` on points transactions is the store's local time with no offset, as the
  point-of-sale feed sends it. Every other time is UTC and ends in `Z`.
- **Late events:** `updated_since` filters on when the platform *received* a row (`recorded_at`, or `updated_at`
  for members and campaigns). About 3% of rows arrive two to seven days after they happened, so an incremental
  client must look back further than its last run.
- **No shared IDs:** members have their own IDs (`LM...`) and the platform's own store codes (`PC0042`,
  `CC-WA-017` instead of the store system's `PC-0042` and `CC/WA/017`).

## Where the data lives

A read-only SQLite file, `loyalty.sqlite3`, made by the Pets Central data generator
(`manage.py generate_data`, written to `data/generated/<size>/`). Locally the API opens it from `LOYALTY_DB_PATH`.
On Azure the file sits in a private blob that `LOYALTY_DB_URL` points at. Each Functions instance downloads it once
to its temp folder when it starts, signed in with the Function App's managed identity, so no key or signed link exists. The schema is in [loyalty/schema.sql](loyalty/schema.sql).

## Running it

Copy `.env.example` to `.env` and set `LOYALTY_API_KEYS`. Commands are for PowerShell, from this folder.

```powershell
uv run uvicorn asgi:app --reload      # http://127.0.0.1:8000/docs
uv run pytest
```

With [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local), copy
`local.settings.example.json` to `local.settings.json` and run `func start` to run it the way Azure does.

`requirements.txt` is what Azure Functions installs. Regenerate it after changing dependencies:

```powershell
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt -o requirements.txt
```
