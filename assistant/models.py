from django.conf import settings
from django.db import models
from django.utils import timezone


class Scope(models.Model):
    """Which store an open assistant database session may see, keyed by the session's server process id.

    The app writes a row before the assistant's login runs any SQL and deletes it after. The assistant's login can't
    read or change this table: the store_data views read it as their owner, so a query can't pick another store.
    """

    backend_pid = models.IntegerField(primary_key=True)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assistant_scope'


class Question(models.Model):
    """A question a manager asked the Store Assistant, with its answer. Kept as an audit log."""

    class Outcome(models.TextChoices):
        ANSWERED = 'answered', 'Answered'
        DECLINED = 'declined', 'Declined'
        FAILED = 'failed', 'Failed'

    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, related_name='assistant_questions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                             related_name='assistant_questions')
    asked_at = models.DateTimeField(default=timezone.now)
    text = models.TextField()
    answer = models.TextField(blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome, default=Outcome.FAILED)
    error = models.TextField(blank=True)
    model = models.CharField(max_length=64)
    policy_search = models.BooleanField(help_text='Whether policy search was available for this question.')
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-asked_at']
        indexes = [models.Index(fields=['store', 'asked_at'], name='question_store_asked_at_idx')]

    def __str__(self):
        return self.text[:80]


class ToolCall(models.Model):
    """One step the assistant took to answer: a SQL query or a policy search."""

    class Tool(models.TextChoices):
        RUN_SQL = 'run_sql', 'Query store data'
        SEARCH_POLICIES = 'search_policies', 'Search policies'

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='tool_calls')
    step = models.PositiveSmallIntegerField()
    tool = models.CharField(max_length=32, choices=Tool)
    input = models.JSONField()
    ok = models.BooleanField(default=False)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    # For SQL, the columns and first rows. For policy search, the sections found, which answers cite.
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['question', 'step']

    def __str__(self):
        return f'{self.question_id} step {self.step}: {self.tool}'
