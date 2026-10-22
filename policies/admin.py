from django.contrib import admin

from .models import Policy


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'version', 'status', 'effective_on', 'applies_to_states', 'owner']
    list_filter = ['status', 'category']
    search_fields = ['title', 'summary', 'body']
    prepopulated_fields = {'slug': ['title']}
