"""Workflows that change several tables at once. Each runs in one database transaction."""

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from catalog.models import Product
from inventory.models import Animal, StockLevel

from .models import Sale, SaleLine, SaleReturn, SaleReturnLine

CENT = Decimal('0.01')


class SaleError(Exception):
    pass


class InsufficientStock(SaleError):
    pass


@dataclass
class LineRequest:
    product: Product
    quantity: int = 1
    animal: Animal | None = None
    discount_amount: Decimal = Decimal('0.00')


@dataclass
class ReturnRequest:
    sale_line: SaleLine
    quantity: int
    restock: bool = True


def new_number(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:12].upper()}'


def price_at(product, moment):
    price = product.prices.filter(valid_from__lte=moment).exclude(valid_to__lte=moment).first()
    if price is None:
        raise SaleError(f'{product.sku} has no price on {moment:%Y-%m-%d}.')
    return price


@transaction.atomic
def record_sale(store, lines, *, customer=None, employee=None, sold_at=None,
                channel=Sale.Channel.IN_STORE, coupon_code=''):
    """Record a sale, lower stock and claim any animals sold. Raises SaleError and saves nothing on failure."""
    if not lines:
        raise SaleError('A sale needs at least one line.')
    sold_at = sold_at or timezone.now()

    sale = Sale.objects.create(
        receipt_number=new_number('R'),
        store=store,
        customer=customer,
        employee=employee,
        channel=channel,
        sold_at=sold_at,
        coupon_code=coupon_code,
    )

    # Lock stock rows in a fixed order so two registers selling the same items can't deadlock.
    stock_needed = {}
    for request in lines:
        if request.quantity < 1:
            raise SaleError(f'Quantity of {request.product.sku} must be at least 1.')
        if not request.product.is_live_animal:
            product, quantity = stock_needed.get(request.product.pk, (request.product, 0))
            stock_needed[product.pk] = (product, quantity + request.quantity)
    for product_id in sorted(stock_needed):
        product, quantity = stock_needed[product_id]
        updated = StockLevel.objects.filter(
            store=store,
            product=product,
            quantity_on_hand__gte=quantity,
        ).update(quantity_on_hand=F('quantity_on_hand') - quantity)
        if not updated:
            raise InsufficientStock(f'Not enough {product.sku} in stock at {store.store_code}.')

    for number, request in enumerate(lines, start=1):
        product = request.product
        animal = None
        if product.is_live_animal:
            if request.animal is None or request.quantity != 1:
                raise SaleError(f'{product.sku} is a live animal: sell exactly one, and say which.')
            animal = Animal.objects.select_for_update(of=('self',)).available().filter(
                pk=request.animal.pk, store=store, product=product,
            ).first()
            if animal is None:
                raise SaleError(f'Animal {request.animal.pk} is not available at {store.store_code}.')
        elif request.animal is not None:
            raise SaleError(f'{product.sku} is not a live animal.')

        price = price_at(product, sold_at)
        SaleLine.objects.create(
            sale=sale,
            line_number=number,
            product=product,
            animal=animal,
            quantity=request.quantity,
            unit_price=price.list_price,
            unit_cost=price.unit_cost,
            discount_amount=request.discount_amount,
        )
    return sale


@transaction.atomic
def cancel_sale(sale, *, cancelled_at=None):
    """Cancel a sale with no returns: put stock back and release any animals."""
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.Status.CANCELLED:
        raise SaleError(f'{sale.receipt_number} is already cancelled.')
    if sale.returns.exists():
        raise SaleError(f'{sale.receipt_number} has returns and can no longer be cancelled.')

    for line in sale.lines.select_related('product').order_by('product_id'):
        if line.animal_id is not None:
            # The line keeps the product, so the cancelled sale still shows an animal of that species.
            line.animal = None
            line.save(update_fields=['animal', 'updated_at'])
        else:
            _add_stock(sale.store, line.product, line.quantity)

    sale.status = Sale.Status.CANCELLED
    sale.cancelled_at = cancelled_at or timezone.now()
    sale.save(update_fields=['status', 'cancelled_at', 'updated_at'])
    return sale


@transaction.atomic
def record_return(sale, store, requests, *, reason, employee=None, returned_at=None):
    """Return items from a completed sale at any store. Refunds the price paid, after discounts."""
    if not requests:
        raise SaleError('A return needs at least one line.')
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.COMPLETED:
        raise SaleError(f'{sale.receipt_number} is not a completed sale.')

    sale_return = SaleReturn.objects.create(
        return_number=new_number('RT'),
        sale=sale,
        store=store,
        employee=employee,
        reason=reason,
        returned_at=returned_at or timezone.now(),
    )
    for request in requests:
        line = request.sale_line
        if line.sale_id != sale.pk:
            raise SaleError(f'Line {line.pk} is not part of {sale.receipt_number}.')
        already = line.return_lines.aggregate(n=Sum('quantity'))['n'] or 0
        if request.quantity < 1 or already + request.quantity > line.quantity:
            raise SaleError(f'Can return at most {line.quantity - already} of line {line.line_number}.')

        refund = (line.line_total * request.quantity / line.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        # Returned animals go to quarantine and are never resold, so they are not restocked.
        restock = request.restock and line.animal_id is None
        SaleReturnLine.objects.create(
            sale_return=sale_return,
            sale_line=line,
            quantity=request.quantity,
            refund_amount=refund,
            restocked=restock,
        )
        if restock:
            _add_stock(store, line.product, request.quantity)
    return sale_return


def _add_stock(store, product, quantity):
    stock, _ = StockLevel.objects.select_for_update().get_or_create(store=store, product=product)
    stock.quantity_on_hand = F('quantity_on_hand') + quantity
    stock.save(update_fields=['quantity_on_hand'])
