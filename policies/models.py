import markdown
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class PolicyQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Policy.Status.PUBLISHED)

    def for_state(self, state):
        """Policies that apply in a state: company-wide ones, and ones that name the state."""
        return self.filter(Q(applies_to_states='') | Q(applies_to_states__regex=rf'(^|,){state}(,|$)'))


class Policy(models.Model):
    """A corporate policy document. Corporate users write them in the admin; store managers read them in the app."""

    class Category(models.TextChoices):
        RETURNS = 'returns', 'Refunds and returns'
        PRICING = 'pricing', 'Coupons and pricing'
        CASH = 'cash', 'Cash handling and shrink'
        INVENTORY = 'inventory', 'Inventory'
        ANIMALS = 'animals', 'Live animals'
        STAFFING = 'staffing', 'Staffing'
        SAFETY = 'safety', 'Incidents and safety'
        LOYALTY = 'loyalty', 'Loyalty program'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        SUPERSEDED = 'superseded', 'Superseded'

    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=16, choices=Category)
    version = models.CharField(max_length=16)
    effective_on = models.DateField()
    status = models.CharField(max_length=16, choices=Status, default=Status.DRAFT)
    owner = models.CharField(max_length=80, help_text='The team that owns this policy, such as Store Operations.')
    # Blank means the policy applies everywhere. Otherwise a comma-separated list of state codes, such as CA,WA.
    applies_to_states = models.CharField(max_length=200, blank=True)
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text='Markdown. Use ## headings for numbered sections so answers can cite them.')
    updated_at = models.DateTimeField(auto_now=True)

    objects = PolicyQuerySet.as_manager()

    class Meta:
        ordering = ['category', 'title']
        verbose_name_plural = 'policies'
        constraints = [
            models.UniqueConstraint(fields=['slug', 'version'], name='policy_unique_version'),
            models.UniqueConstraint(fields=['slug'], condition=Q(status='published'),
                                    name='one_published_version_per_policy'),
        ]

    def __str__(self):
        return f'{self.title} (v{self.version})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def states(self):
        return [s for s in self.applies_to_states.split(',') if s]

    def render(self):
        """The body as HTML, with an id on every heading so answers and links can point at a section."""
        converter = markdown.Markdown(extensions=['tables', 'toc', 'sane_lists'],
                                      extension_configs={'toc': {'permalink': False}})
        html = converter.convert(self.body)
        return html, converter.toc_tokens
