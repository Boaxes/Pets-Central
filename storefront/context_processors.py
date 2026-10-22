from django.conf import settings

from stores.models import Store


def storefront(request):
    is_corporate = getattr(request, 'is_corporate', False)
    return {
        'demo_sign_in': settings.DEMO_SIGN_IN,
        'all_stores': Store.objects.filter(closed_on__isnull=True).order_by('store_code') if is_corporate else [],
    }
