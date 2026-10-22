from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from policies.models import Policy

from .access import store_required


def _visible(request):
    """Published policies that apply in this store's state."""
    return Policy.objects.published().for_state(request.store.state)


@store_required
def policy_list(request):
    text = request.GET.get('q', '').strip()
    policies = _visible(request)
    if text:
        policies = policies.filter(Q(title__icontains=text) | Q(summary__icontains=text) | Q(body__icontains=text))
    order = [value for value, _ in Policy.Category.choices]
    groups = {}
    for policy in sorted(policies, key=lambda p: (order.index(p.category), p.title)):
        groups.setdefault(policy.get_category_display(), []).append(policy)
    return render(request, 'storefront/policies.html', {'groups': groups, 'q': text, 'count': len(policies)})


@store_required
def policy_detail(request, slug):
    policy = get_object_or_404(_visible(request), slug=slug)
    html, toc = policy.render()
    return render(request, 'storefront/policy.html', {'policy': policy, 'html': html, 'toc': toc})
