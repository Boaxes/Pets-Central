# Pets Central transformation (dbt)

dbt models that turn the two raw sources in Snowflake (`PETS_CENTRAL.RAW`) into tested tables for analysis. The
project has its own `pyproject.toml` because dbt pins library versions the loaders don't share.

```
RAW (both sources, every version of every row)
  └─ STAGING        one view per source table: latest version, renamed, UTC, normalized contact details
       └─ INTERMEDIATE   who is who: customer records → people, loyalty members → people
            └─ MARTS          dimensions and facts for Power BI
                 EVALUATION   how well the matching and the campaign measure did, against the generator's truth
```

## Layers

**Staging** (`models/staging/`, views). One model per raw table. RAW keeps every version of a row the loaders
saw, so each model keeps the latest per id. Times become UTC `TIMESTAMP_NTZ`. The loyalty JSON is parsed into
columns. The cleaning rules live in [macros/normalize.sql](macros/normalize.sql), so both sources clean the same way:

| Rule | Example |
|---|---|
| Emails: trim, lowercase, fix known domain typos (`vars.email_domain_typos`) | `Sam.Rivera@Mailbox.Exmaple ` → `sam.rivera@mailbox.example` |
| Phones: digits only, drop a leading US 1, ten digits or null | `+1 (206) 555-0142` → `2065550142` |
| Loyalty store codes to store-system codes | `PC0042` → `PC-0042`, `CC-WA-017` → `CC/WA/017` |
| Coupon codes: uppercase, no spaces | `dog15 - 240512` → `DOG15-240512` |
| Local times to UTC with the store's time zone | points `occurred_at` |

**Intermediate** (`models/intermediate/`). The identity work:

- `int_customer_people` groups customer records into people. Two records are the same person when they share a
  normalized email or phone, directly or through another record. The groups are connected components, found by
  label propagation: each record takes the smallest id among records it shares a detail with, for six rounds.
  `assert_customer_people_converged` fails if a seventh round would change anything.
- `int_member_matches` matches each loyalty member to a person. The two systems share no ID, so it uses three
  rules, strongest first, each used only when the stronger ones found no one:
  1. email
  2. phone and last name
  3. first name, last name and postal code

  A member whose evidence points at more than one person stays unmatched rather than guessed at.
- `int_person_members` keeps at most one membership per person.

**Marts** (`models/marts/`, tables). `dim_date`, `dim_stores`, `dim_products`, `dim_customers` (one row per person,
duplicates merged, with loyalty membership and purchase history), `dim_campaigns`; `fct_sale_lines`, `fct_sales`,
`fct_returns`, `fct_points_transactions`, `fct_email_events`, `fct_coupon_redemptions`, `fct_stock_levels`; and
`campaign_performance`.

**Evaluation** (`models/evaluation/`). The generator writes a truth file of which customer records each member really
is, and each campaign's true effect. They are loaded as seeds and used only to score the work, never as inputs:
`matching_scorecard` (precision and recall per rule) and `campaign_lift_check` (naive lift against true lift).

## Results of the first full build (2026-10-16)

The full build (40 models and 96 tests, against 10.7 million sale lines) took 38 seconds on an extra-small
warehouse, and every test passed.

**Customer matching**, scored against the truth file:

| Rule | Members | Correct | Precision |
|---|---|---|---|
| Email and phone agree | 96,325 | 96,325 | 100% |
| Email only | 29,415 | 29,414 | 99.997% |
| Phone and last name | 37,797 | 37,797 | 100% |
| Name and postal code | 9,761 | 9,751 | 99.9% |
| **All matched** | **173,298** | **173,287** | **99.99%** |

Recall is 99.05%: of the 174,951 members who really are store customers, 1,642 share no email, phone, or unique
name and postal code with their customer record, and 21 more were ambiguous. Email and phone alone reached 93.5%
recall; the name and postal code rule added 5.5 points at a cost of 10 wrong matches. 93% of people entered
twice had their records merged; the rest share no email or phone across their two records.

**Campaign measurement.** The naive measure in `campaign_performance` (the department's daily sales during a
campaign against the days just before) ranks campaigns fairly well against their true effect (rank correlation
0.77), but 6 of the 8 campaigns that did nothing still show about 7% "lift", from seasonality and coupon users who
would have bought anyway. Measuring a campaign properly needs a holdout group.

## Tests

Besides unique, not-null, relationship and accepted-value tests on every key, these check that the sources agree:

- `assert_coupon_redemptions_reconcile_with_store_sales`: for every campaign, the loyalty platform's redemptions
  match the store's coupon sales in count and money.
- `assert_member_points_balance_matches_ledger`: every member's balance is the sum of their transactions.
- `assert_sale_line_amounts_are_consistent`: net is gross less discount, and nothing is negative.
- `assert_customer_people_converged`: the people grouping is complete.

Relationship tests also prove that every coupon code typed at the register, and every store code the loyalty
platform uses, maps to a real campaign or store.

## Running it

From this folder, in PowerShell. Connection settings come from the project's `.env`.

```powershell
uv run dbt deps
uv run dotenv -f ../.env run -- dbt seed      # the evaluation truth files, from data/generated/full/
uv run dotenv -f ../.env run -- dbt build     # every model and test
uv run dotenv -f ../.env run -- dbt docs generate
```
