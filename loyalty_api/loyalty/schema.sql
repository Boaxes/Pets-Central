-- The loyalty platform's database. The vendor owns this schema; the Pets Central data generator fills it.
-- Times ending in _at are UTC ISO 8601 strings ending in Z, except points_transactions.occurred_local, which is the
-- store's local wall-clock time with no offset, as the point-of-sale feed sends it.
-- recorded_at is when the platform received a row. Late events have a recorded_at days after they happened.

CREATE TABLE members (
    id INTEGER PRIMARY KEY,
    member_id TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,                      -- Lowercased and trimmed by the platform at signup.
    phone_typed TEXT,                -- As the member typed it. v1 returns this.
    phone_e164 TEXT,                 -- Normalized, such as +13605550142. v2 returns this.
    postal_code TEXT,
    home_store_code TEXT,            -- The platform's own store codes, such as PC0042 or CC-WA-017.
    home_store_time_zone TEXT,
    pet_types TEXT NOT NULL,         -- Comma-separated department codes, such as DOG,CAT.
    email_opt_in INTEGER NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL,
    enrolled_at TEXT NOT NULL,
    closed_at TEXT,
    points_balance INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX members_updated ON members (updated_at, id);

CREATE TABLE campaigns (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    department_code TEXT NOT NULL,
    discount_percent INTEGER NOT NULL,
    starts_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    channel TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX campaigns_updated ON campaigns (updated_at, id);

CREATE TABLE points_transactions (
    id INTEGER PRIMARY KEY,
    member_id TEXT NOT NULL,
    type TEXT NOT NULL,              -- earn, campaign_bonus, reversal, redeem
    points INTEGER NOT NULL,
    purchase_amount REAL,
    store_code TEXT,
    occurred_local TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX points_recorded ON points_transactions (recorded_at, id);

CREATE TABLE email_events (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    member_id TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    opened_at TEXT,
    clicked_at TEXT,
    unsubscribed INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX email_recorded ON email_events (recorded_at, id);
CREATE INDEX email_campaign ON email_events (campaign_id, recorded_at, id);

CREATE TABLE coupon_redemptions (
    id INTEGER PRIMARY KEY,
    redemption_id TEXT NOT NULL UNIQUE,
    campaign_id INTEGER NOT NULL,
    coupon_code TEXT NOT NULL,
    member_id TEXT,                  -- Null when the code was used by someone who isn't a member.
    store_code TEXT NOT NULL,
    redeemed_at TEXT NOT NULL,
    order_total REAL NOT NULL,
    discount_amount REAL NOT NULL,
    status TEXT NOT NULL,            -- redeemed, voided
    voided_at TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX redemptions_recorded ON coupon_redemptions (recorded_at, id);
