from django.contrib.auth import views as auth_views
from django.urls import path

from assistant import views as assistant

from . import pages
from .tables import table_view
from .views import auth, home, policies, sales
from .views.access import store_required


def _table(page):
    return store_required(lambda request: table_view(request, page))


urlpatterns = [
    path('', home.home, name='home'),
    path('sales/', sales.sales, name='sales'),
    path('customers/', _table(pages.customers), name='customers'),
    path('animals/', _table(pages.animals), name='animals'),
    path('employees/', _table(pages.employees), name='employees'),
    path('caretakers/', _table(pages.caretakers), name='caretakers'),
    path('products/', _table(pages.products), name='products'),
    path('categories/', _table(pages.categories), name='categories'),
    path('policies/', policies.policy_list, name='policies'),
    path('policies/<slug:slug>/', policies.policy_detail, name='policy'),
    path('assistant/', assistant.assistant, name='assistant'),
    path('assistant/<int:pk>/', assistant.question_detail, name='assistant_question'),
    path('accounts/login/', auth.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/demo/', auth.demo_sign_in, name='demo_sign_in'),
    path('switch-store/', auth.switch_store, name='switch_store'),
]
