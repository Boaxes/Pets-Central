from zoneinfo import ZoneInfo

from django.utils import timezone

from .scoping import is_corporate, store_for


class CurrentStoreMiddleware:
    """Puts the signed-in user's store on every request as request.store. Every page filters by it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Worked out up front, not lazily: `request.store is None` must be a real check for pages to rely on.
        request.is_corporate = is_corporate(request.user)
        request.store = store_for(request)
        # Show every date and time on the store's own clock: an 8 pm sale on the 30th is the 30th, not the 1st.
        if request.user.is_authenticated and request.store is not None:
            timezone.activate(ZoneInfo(request.store.time_zone))
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
