"""Which store a signed-in user may see. A store manager sees only their own store; corporate users pick any store."""

from stores.models import Store

CORPORATE_GROUP = 'Corporate'
MANAGER_GROUP = 'Store Managers'
SESSION_STORE_KEY = 'corporate_store_id'


def is_corporate(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=CORPORATE_GROUP).exists())


def store_for(request):
    """The store this request is about, or None when the user may not see any store."""
    user = request.user
    if not user.is_authenticated:
        return None
    if request.is_corporate:
        stores = Store.objects.select_related('region')
        return (stores.filter(pk=request.session.get(SESSION_STORE_KEY)).first()
                or stores.filter(closed_on__isnull=True).order_by('store_code').first())
    employee = getattr(user, 'employee', None)
    if employee is None or employee.terminated_on is not None:
        return None
    return Store.objects.select_related('region').get(pk=employee.store_id)
