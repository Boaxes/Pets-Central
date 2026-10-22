from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from storefront.views.access import store_required

from . import agent, policy_search
from .models import Question
from .rendering import render_answer

EXAMPLES = [
    'What were our best-selling products last month?',
    'Which animals have been here longest without selling?',
    'How did revenue this quarter compare with the same quarter last year?',
    'Which products are below their reorder point, and how fast do they sell?',
]
POLICY_EXAMPLES = [
    'Can I refund a bag of food that was opened, without a receipt?',
    'A gecko died 10 days after it was sold. What do we owe the customer?',
]


class QuestionForm(forms.Form):
    question = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={'rows': 3}), label='Your question',
                               label_suffix='')


def _context(request, **extra):
    ready, not_ready = agent.status()
    use_policies = policy_search.is_available()
    return {
        'ready': ready,
        'not_ready': not_ready,
        'policy_search': use_policies,
        'examples': EXAMPLES + (POLICY_EXAMPLES if use_policies else []),
        'recent': Question.objects.filter(store=request.store).select_related('user')[:15],
        'left_today': agent.questions_left_today(request.user),
        **extra,
    }


def _answer_context(question):
    sections = {s['key']: s for call in question.tool_calls.all() if call.result for s in call.result.get('sections', [])}
    answer_html, citations = render_answer(question.answer, sections)
    return {'question': question, 'answer_html': answer_html, 'citations': citations,
            'calls': question.tool_calls.all()}


@store_required
def assistant(request):
    form = QuestionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ready, not_ready = agent.status()
        if not ready:
            messages.error(request, not_ready)
        elif not agent.questions_left_today(request.user):
            messages.error(request, "Today's limit of questions has been reached. The assistant will be back tomorrow.")
        else:
            question = agent.ask(request.store, request.user, form.cleaned_data['question'])
            if _is_htmx(request):
                response = render(request, 'assistant/_answer.html', _answer_context(question))
                response['HX-Push-Url'] = question_url(question)
                return response
            return redirect(question_url(question))
        if _is_htmx(request):
            return render(request, 'assistant/_message.html')
    return render(request, 'assistant/assistant.html', _context(request, form=form))


@store_required
def question_detail(request, pk):
    question = get_object_or_404(Question.objects.filter(store=request.store), pk=pk)
    return render(request, 'assistant/assistant.html',
                  _context(request, form=QuestionForm(), **_answer_context(question)))


def question_url(question):
    return reverse('assistant_question', args=[question.pk])


def _is_htmx(request):
    return request.headers.get('HX-Request') == 'true'
