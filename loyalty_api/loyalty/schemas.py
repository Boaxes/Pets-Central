"""Response shapes. FastAPI validates every response against these and documents them at /docs."""

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    data: list[T]
    next_cursor: str | None = Field(description='Pass as `cursor` to get the next page. Null on the last page.')
    has_more: bool


class MemberV2(BaseModel):
    member_id: str
    first_name: str
    last_name: str
    email: str | None
    phone_e164: str | None
    postal_code: str | None
    home_store: str | None
    pet_types: list[str]
    email_opt_in: bool
    tier: str
    status: str
    enrolled_at: str
    closed_at: str | None
    points_balance: int
    updated_at: str


class MemberV1(BaseModel):
    id: str
    name: str = Field(description='"Last, First".')
    email_address: str | None
    phone: str | None = Field(description='As the member typed it.')
    signup_date: str = Field(description="MM/DD/YYYY HH:MM in the home store's local time.")
    tier: str
    points: int


class MembersV1Page(BaseModel):
    members: list[MemberV1]
    page: int
    page_size: int
    total: int


class Campaign(BaseModel):
    campaign_id: int
    code: str
    name: str
    department: str
    discount_percent: int
    starts_on: str
    ends_on: str
    channel: str
    updated_at: str


class PointsTransaction(BaseModel):
    transaction_id: int
    member_id: str
    type: str = Field(description='earn, campaign_bonus, reversal or redeem.')
    points: int
    purchase_amount: float | None
    store_code: str | None
    occurred_at: str = Field(description="The store's local time, with no offset, as the point-of-sale feed sends it.")
    recorded_at: str = Field(description='When the platform received it, in UTC.')


class EmailEvent(BaseModel):
    event_id: int
    campaign_id: int
    member_id: str
    sent_at: str
    opened_at: str | None
    clicked_at: str | None
    unsubscribed: bool
    recorded_at: str


class CouponRedemption(BaseModel):
    redemption_id: str
    campaign_id: int
    coupon_code: str
    member_id: str | None = Field(description='Null when someone who is not a member used the code.')
    store_code: str
    redeemed_at: str
    order_total: float
    discount_amount: float
    status: str = Field(description='redeemed or voided.')
    voided_at: str | None
    recorded_at: str
