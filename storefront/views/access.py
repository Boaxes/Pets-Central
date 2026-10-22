from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def store_required(view):
    """Signed in, and allowed to see a store. Every store page uses this, and filters by request.store."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.store is None:
            raise PermissionDenied('Your account is not assigned to a store.')
        return view(request, *args, **kwargs)

    return wrapper
