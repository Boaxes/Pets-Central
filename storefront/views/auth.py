from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import Group
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from stores.locations import store_location
from stores.models import Employee, Store

from ..scoping import MANAGER_GROUP, SESSION_STORE_KEY, is_corporate


def current_manager(store):
    return (Employee.objects.filter(store=store, role=Employee.Role.STORE_MANAGER, terminated_on__isnull=True)
            .order_by('-hired_on').first())


def demo_sign_in(request):
    """A map of the stores. Picking one opens the sign-in form with its manager's username and password filled in.

    Only when DEMO_SIGN_IN is on, with DEMO_PASSWORD set.
    """
    if not settings.DEMO_SIGN_IN or not settings.DEMO_PASSWORD:
        raise Http404
    if request.method == 'POST':
        store = get_object_or_404(Store, pk=request.POST.get('store'), closed_on__isnull=True)
        manager = current_manager(store)
        if manager is None:
            messages.error(request, f'{store} has no manager right now.')
            return redirect('demo_sign_in')
        user = manager_user(manager)
        return redirect(f"{reverse('login')}?{urlencode({'username': user.username})}")
    stores = list(Store.objects.filter(closed_on__isnull=True).select_related('region').order_by('state', 'city', 'name'))
    managers = {e.store_id: e for e in Employee.objects.filter(
        store__in=stores, role=Employee.Role.STORE_MANAGER, terminated_on__isnull=True).order_by('hired_on')}
    points = []
    for store in stores:
        latitude, longitude = store_location(store)
        manager = managers.get(store.pk)
        points.append({'id': store.pk, 'code': store.store_code, 'name': store.name, 'city': store.city,
                       'state': store.state, 'region': store.region.name, 'lat': latitude, 'lng': longitude,
                       'manager': f'{manager.first_name} {manager.last_name}' if manager else None,
                       'acquired': store.original_chain == Store.Chain.CRITTER_CORNER})
    states = {}
    for store in stores:
        states.setdefault(store.state, []).append(store)
    return render(request, 'storefront/demo_sign_in.html', {'points': points, 'states': states,
                                                             'store_count': len(stores)})


def manager_user(manager):
    """The manager's sign-in account, created the first time it's needed, with the demo password."""
    user = manager.user
    if user is None:
        user = get_user_model().objects.create(
            username=slugify(f'{manager.first_name}-{manager.last_name}-{manager.employee_number}'),
            first_name=manager.first_name, last_name=manager.last_name, email=manager.email,
        )
        user.groups.add(Group.objects.get_or_create(name=MANAGER_GROUP)[0])
        manager.user = user
        manager.save(update_fields=['user'])
    if settings.DEMO_SIGN_IN and settings.DEMO_PASSWORD and not user.check_password(settings.DEMO_PASSWORD):
        user.set_password(settings.DEMO_PASSWORD)
        user.save(update_fields=['password'])
    return user


class LoginView(auth_views.LoginView):
    """Django's sign-in page. In the demo, a store picked on the map arrives with its manager's details filled in."""

    def get_initial(self):
        initial = super().get_initial()
        if self.demo_username():
            initial.update(username=self.demo_username(), password=settings.DEMO_PASSWORD)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.demo_username():
            form.fields['password'].widget.render_value = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        username = self.demo_username()
        if username:
            context['demo_manager'] = (Employee.objects.filter(user__username=username)
                                       .select_related('store').first())
        return context

    def demo_username(self):
        if settings.DEMO_SIGN_IN and settings.DEMO_PASSWORD and self.request.method == 'GET':
            return self.request.GET.get('username', '')
        return ''


@require_POST
def switch_store(request):
    """Corporate users can look at any store."""
    if not is_corporate(request.user):
        raise Http404
    request.session[SESSION_STORE_KEY] = get_object_or_404(Store, pk=request.POST.get('store')).pk
    return redirect(request.POST.get('next') or 'home')
