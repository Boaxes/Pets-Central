# Pets Central

Pets Central is a fictional chain of 200 pet stores with three years of history: 4.3 million sales, 500,000
customer records, and a loyalty program run by another company. This repository is its data platform, built the way
a large company would build one: a Django store app and a loyalty vendor's API on Azure, loaded by Dagster into
Snowflake, modeled and tested by dbt, analyzed with Power BI and AI, and deployed with Terraform through GitHub
Actions.

## Live Demos

| Demo | What to try |
|---|---|
| [Store App](https://pets-store-demo.whiteglacier-1d4f68cb.centralus.azurecontainerapps.io/) | Pick a store on the map to sign in as its manager, then ask the Store Assistant about the store's sales or its policies. |
| [Analytics App](https://pets-central-analytics.streamlit.app/) | Explore the marts, and ask a question in plain English on the Ask page. |
| [Pawprint Loyalty Rewards API](https://pawprint-loyalty-docs.pages.dev) | The vendor API's docs, with a public demo key filled in, so Try It Out makes real calls. |

The writeup, with screenshots of every piece running in production, is at
[brandonconnely.com](https://brandonconnely.com/portfolio/projects/pets-central). The Power BI report is in
[analytics/powerbi/](analytics/powerbi/PetsCentral.pdf).

The demos run on the `small` dataset and cost almost nothing while idle: the store app scales to zero on Azure
Container Apps, its database is a Neon branch reset to a clean copy every night, the Rewards API bills per request,
and the public analytics app reads a copy of the marts in Neon, with Claude answering in place of Snowflake's Cortex
Analyst.

## Architecture

```
                 Azure                                          External vendor
  ┌──────────────────────────────────────────────┐
  │  Store App (Django, Container Apps)          │       Pawprint Loyalty Rewards API
  │        │                                     │       (FastAPI, Azure Functions)
  │  Store Database (Postgres + pgvector)        │                 │
  │        │                                     │                 │
  │        └──────────► Dagster (Container Apps) ◄─────────────────┘
  └──────────────────────────────│───────────────┘
                                 ▼
  Snowflake     RAW ──► dbt (run by Dagster) ──► MARTS ──► AI Analytics App (Streamlit + Cortex)
                                                   └─────► Power BI

  DevOps: GitHub Actions + Terraform deploy both Azure and Snowflake
```

| Piece | Where | Folder |
|---|---|---|
| Store app and database | Django 6.1 on Postgres 18 with pgvector | [stores/](stores/), [catalog/](catalog/), [customers/](customers/), [inventory/](inventory/), [sales/](sales/), [policies/](policies/), [storefront/](storefront/) |
| Store Assistant | Claude with two tools: SQL over the manager's own store, and policy search with pgvector | [assistant/](assistant/) |
| Data generator | Three years of history, messy on purpose, with the truth written down to score against | [datagen/](datagen/) |
| Rewards API | The loyalty vendor's API: FastAPI on Azure Functions | [loyalty_api/](loyalty_api/README.md) |
| Loaders | Postgres and the Rewards API into Snowflake's RAW schema | [pipeline/](pipeline/) |
| Orchestration | Dagster: 61 assets and 91 checks on one daily schedule | [orchestration/](orchestration/) |
| Transformation | dbt: staging, customer matching and a star schema of marts, with 94 tests | [transform/](transform/README.md) |
| Analytics | Power BI, and a Streamlit app with Cortex Analyst | [analytics/](analytics/) |
| Infrastructure | Terraform stacks for Azure, the vendor and Snowflake | [infra/](infra/README.md) |
| CI/CD | GitHub Actions: tests, dbt build and Terraform plans on every pull request; deploys on merge | [.github/workflows/](.github/workflows/) |

## Store App

A Django app on Postgres, split by feature area:

| App | Models |
|---|---|
| `stores` | `Region`, `Store`, `Employee` |
| `catalog` | `Department`, `Category`, `Brand`, `Species`, `Product`, `ProductPrice` (price history) |
| `customers` | `Customer` |
| `inventory` | `StockLevel`, `Animal` (each live animal tracked individually) |
| `sales` | `Sale`, `SaleLine`, `SaleReturn`, `SaleReturnLine` |
| `policies` | The corporate policies every store follows, with an embedding of each section |

Recording a sale, cancelling it and returning items all go through `sales/services.py`, which does the whole
change in one transaction: it copies the price and cost in effect at the time of sale, lowers stock, claims any
animal sold, and rolls everything back if any part fails.

Some design choices:

- Deleting a sale never deletes the animals it sold, and a customer with sales can't be deleted (`PROTECT`).
- An animal's availability has one source: it is available when it has no sale line and hasn't been removed.
- Species is a lookup table, not free text, and animals store a birth date, not an age.
- Sale totals are calculated from the lines (`Sale.objects.with_totals()`), never stored.
- Sale lines keep the unit price and cost at the time of sale, so price changes never rewrite history.

Customer emails and phone numbers are stored as staff typed them. Cleaning and matching them is the warehouse's job.

The Store Assistant answers a manager's questions. For numbers it writes SQL, which runs as a read-only login over
views bound to the manager's store, so however the SQL is written it can't see another store's rows. For rules it
searches the policy sections with pgvector and cites the ones it used. Every question, query and answer is logged.

## Generated History

`manage.py generate_data` creates three years of history (October 2023 to September 2026) and bulk-loads it with
Postgres `COPY`. The same `--seed` and `--size` always produce the same data.

| Size | Stores | Products | Customers | Sale lines |
|---|---|---|---|---|
| `tiny` | 6 | 400 | 800 | about 16,000 |
| `small` (default) | 20 | 1,500 | 10,000 | about 250,000 |
| `medium` | 100 | 8,000 | 120,000 | about 2.5 million |
| `full` | 200 | 15,000 | 500,000 | about 10 million |

What the history contains:

- **Patterns:** a December peak, Black Friday, closures on Thanksgiving and Christmas, busy weekends, flea and
  tick season, spring animal sales and 5% yearly growth. Prices rise over time and sale lines keep the price of
  their day. House-brand products have higher margins.
- **Customers:** one-time and repeat shoppers who eventually stop coming, plus guest checkouts with no customer.
- **Campaigns:** coupon campaigns from the loyalty platform bring opted-in customers in and show up as coupon
  codes and discounts. Each campaign's real effect varies, and some do nothing; the true effects are written to
  `data/generated/<size>/campaign_true_lift.csv` to check the analysis against.
- **Mess, on purpose:** the same person entered twice with different email capitalization, phone numbers in
  seven formats, missing emails and phones, the odd email typo or trailing space, coupon codes typed in
  lowercase, cancelled sales and returns. The stores from the Critter Corner acquisition (April 2025) use
  `CC/WA/017`-style store codes and `CC-` employee numbers, and their customers were all imported in one batch.
- **Live animals:** every animal sold is a specific animal that arrived at that store shortly before, cared
  for by that store's staff. Some animals are still waiting in stores at the end.

```powershell
uv run python manage.py generate_data --size full --reset
```

`--reset` deletes the existing store data first; admin logins are kept.

## Rewards API

The second data source is the loyalty program, run by a fictional vendor, Pawprint Loyalty. Its API lives in
[loyalty_api/](loyalty_api/README.md) with its own `pyproject.toml`: a FastAPI app hosted in Azure Functions,
serving members, points, campaigns, campaign emails and coupon redemptions. It behaves like a real vendor API: API
keys, rate limits, occasional 503s, v1 and v2 with renamed fields, local times mixed with UTC, and events that
arrive days late.

Its data is a read-only SQLite file made by `generate_data` from the same people and purchases as the store data,
so the two sources agree. Members share no ID with store customers, and their emails and phones were recorded
differently, which is what the dbt customer matching has to solve. `loyalty_member_truth.csv`, written next to it
and never served by the API, says which member is which customer, so the matching can be scored.

## Loading Into Snowflake

`pipeline/load_store_ops.py` copies the store tables into `PETS_CENTRAL.RAW`, as `STORE_OPS__<table>`, loading
only what changed since the last run:

| Strategy | Tables | What a run loads |
|---|---|---|
| Incremental | customers, sales, sale lines, animals, prices | Rows whose `updated_at` is at or after the newest one in RAW, less a 15-minute overlap for late commits. New versions are appended, so RAW keeps every version of a row; dbt keeps the latest per id. |
| Append | returns, return lines | Rows with an `id` above the highest in RAW. These never change. |
| Full | stores, staff, catalog, stock levels, animal caretakers | The whole table, swapped in at once. |

Each table is exported with Postgres `COPY` as gzipped CSV, uploaded to a table stage and loaded with `COPY INTO`
a loading table. The row count is checked against Postgres before anything reaches RAW, and the count and export
read one consistent snapshot. A failed run leaves RAW as it was. Django's own tables (users, password hashes,
sessions) are never exported.

`pipeline/load_loyalty.py` does the same for the Rewards API. Each v2 endpoint lands in `LOYALTY__<NAME>` as raw
JSON in a `VARIANT` column, next to the record id, the time it changed and the run's batch id, so a renamed or
added field never breaks the load. A run asks for rows changed since the newest one in RAW, less an hour, and the
client honors `Retry-After` on 429s and backs off on 503s and network errors.

In production both loaders run as Dagster assets on Azure Container Apps, followed by `dbt build`, on one daily
schedule.

## Transformation

[transform/](transform/README.md) is the dbt project. It turns RAW into staging views, matches customer records and
loyalty members into people, and builds the marts Power BI and the analytics app read: a star for each fact table
(sales, returns, coupon redemptions and campaign emails). Scored against the generator's truth, the customer
matching has 99.99% precision and 99.05% recall.

## Analytics

- **Power BI** connects directly to Snowflake as a read-only service user and imports the marts as stars. The
  PBIP project, a PDF export and screenshots are in [analytics/powerbi/](analytics/powerbi/).
- **The AI Analytics App** ([analytics/app/](analytics/app/)) is a Streamlit app. In Snowflake it runs as the
  reporting role, and its Ask page sends questions to Cortex Analyst, guided by a semantic model of the marts. The
  public copy on Streamlit Community Cloud reads the marts from Postgres through a read-only login, and Claude
  writes the SQL from the same semantic model.

## Deployment

Every change is a pull request. CI runs the Django and Rewards API tests, builds and tests dbt in the pull
request's own Snowflake schemas, checks the Dagster definitions, builds the Docker images and posts the Terraform
plan for every stack. Merging deploys: GitHub Actions signs in to Azure with OIDC, so no password is stored, then
pushes the images and applies the plans. Secrets live in Azure Key Vault, and Snowflake's loader, dbt and reporting
users each sign in with their own key pair and role. See [infra/](infra/README.md) for the stacks and how to set
them up from nothing.

Production ran on Azure for the screenshots in [docs/screenshots/](docs/screenshots/), then was destroyed with
`destroy.yml`, leaving the low-cost demos above.

## Running It Locally

Requires [uv](https://docs.astral.sh/uv/) and Postgres 18 with pgvector. Commands are for PowerShell.

1. Copy `.env.example` to `.env` and fill in a secret key and a database password:

   ```powershell
   Copy-Item .env.example .env
   uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

2. Create the database role and database from the values in `.env`. This asks for the `postgres` superuser
   password:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_local_db.ps1
   ```

3. Create the tables, generate some history, make an admin login and start the server:

   ```powershell
   uv run python manage.py migrate
   uv run python manage.py generate_data --size tiny
   uv run python manage.py createsuperuser
   uv run python manage.py runserver
   ```

   The store app is at <http://127.0.0.1:8000/>. The Store Assistant needs an Anthropic API key in `.env`.

4. Run the tests:

   ```powershell
   uv run python manage.py test
   ```

5. The rest of the pipeline needs a Snowflake account (see [infra/](infra/README.md)) and the Snowflake settings
   in `.env`. With those set, start the Rewards API (its key goes in `loyalty_api/.env`, see its
   [README](loyalty_api/README.md)), then, in a second terminal, Dagster, which loads both sources and runs dbt:

   ```powershell
   cd loyalty_api
   uv run uvicorn asgi:app --port 8001
   ```

   ```powershell
   uv run --project orchestration dagster dev   # from the repository root; http://127.0.0.1:3000
   ```
