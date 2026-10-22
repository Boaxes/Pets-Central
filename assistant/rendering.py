"""Turns an answer's markdown into HTML that is safe to show, with policy citations as links.

Answers can repeat text from the data or the policies, so nothing in them is trusted as HTML. Text is escaped before
markdown runs, links and images that markdown would make are removed (an image URL could carry data off the page),
and only citations of sections the assistant actually retrieved become links.
"""

import html
import re

import markdown

CITATION = re.compile(r'\[\[([a-z0-9-]+#[A-Za-z0-9_-]+)\]\]')
LINK = re.compile(r'<a\b[^>]*>(.*?)</a>', re.DOTALL)
IMAGE = re.compile(r'<img\b[^>]*>')
LIST_ITEM = re.compile(r'^\s*(?:[-*+]|\d+\.)\s')


def render_answer(text, sections):
    """sections maps a citation key ('slug#anchor') to the section's details from the policy search."""
    cited = []

    def placeholder(match):
        key = match.group(1)
        if key not in sections:
            return ''
        if key not in cited:
            cited.append(key)
        return f'CITATION{cited.index(key)}MARK'

    body = CITATION.sub(placeholder, html.escape(_separate_lists(text), quote=False))
    body = markdown.markdown(body, extensions=['tables', 'sane_lists'])
    body = IMAGE.sub('', LINK.sub(r'\1', body))
    for number, key in enumerate(cited):
        section = sections[key]
        link = (f'<a class="cite" href="{html.escape(section["url"])}" '
                f'title="{html.escape(section["title"])}: {html.escape(section["heading"])}">[{number + 1}]</a>')
        body = body.replace(f'CITATION{number}MARK', link)
    return body, [sections[key] for key in cited]


def _separate_lists(text):
    """Puts a blank line before a list that starts right under a line of text ("Bring:" then "- A receipt"). Claude
    often writes lists that way, and Python's markdown only starts a list after a blank line."""
    out = []
    for line in text.splitlines():
        if LIST_ITEM.match(line) and out and out[-1].strip() and not LIST_ITEM.match(out[-1]):
            out.append('')
        out.append(line)
    return '\n'.join(out)
