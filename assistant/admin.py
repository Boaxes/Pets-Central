from django.contrib import admin

from .models import Question, ToolCall


class ToolCallInline(admin.TabularInline):
    model = ToolCall
    extra = 0
    can_delete = False
    fields = ['step', 'tool', 'input', 'ok', 'row_count', 'error', 'duration_ms']
    readonly_fields = fields


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """The assistant's audit log: what was asked, by whom, and every query run to answer it."""

    list_display = ['asked_at', 'store', 'user', 'text', 'outcome', 'input_tokens', 'output_tokens', 'duration_ms']
    list_filter = ['outcome', 'policy_search', 'store__region']
    search_fields = ['text', 'answer', 'store__store_code', 'user__username']
    date_hierarchy = 'asked_at'
    inlines = [ToolCallInline]
    readonly_fields = [f.name for f in Question._meta.fields]

    def has_add_permission(self, request):
        return False
