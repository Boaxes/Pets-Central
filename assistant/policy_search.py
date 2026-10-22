"""Policy search: finds the policy sections closest in meaning to a question, with pgvector.

Each published policy is split at its ## headings, and each section is embedded with Azure OpenAI's
text-embedding-3-small and stored in the policy_section table. Search embeds the question the same way and returns the nearest sections that apply in the
store's state. Answers cite sections by policy slug and heading id, which the policy page links to.

It needs the vector extension, which the production database has and local Windows Postgres doesn't. Without it,
or without AZURE_OPENAI_ENDPOINT, the assistant answers from store data only and says policy search isn't available.
Build or rebuild the index with `manage.py index_policies` after policies change.
"""

import re
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.db import connection, transaction
from django.urls import reverse

from config import managed_identity
from policies.models import Policy

DIMENSIONS = 1024  # text-embedding-3-small shortened to 1024; plenty for 55 sections.
BATCH = 64


@dataclass
class Section:
    slug: str
    version: str
    title: str
    owner: str
    anchor: str
    heading: str
    body: str
    policy_id: int = 0

    @property
    def key(self):
        return f'{self.slug}#{self.anchor}'

    @property
    def url(self):
        return f"{reverse('policy', args=[self.slug])}#{self.anchor}"

    def text_to_embed(self):
        return f'{self.title}\n{self.heading}\n\n{self.body}'

    def as_dict(self):
        return {'key': self.key, 'title': self.title, 'version': self.version, 'heading': self.heading,
                'url': self.url}


def split_sections(policy):
    """A policy's ## sections, with the same heading ids its page uses, so citations link to the right place."""
    _, toc = policy.render()
    anchors = [token['id'] for token in _flatten(toc) if token['level'] == 2]
    parts = re.split(r'^## +(.+?)\s*$', policy.body, flags=re.MULTILINE)
    headings, bodies = parts[1::2], parts[2::2]
    if len(anchors) != len(headings):
        raise ValueError(f'{policy.slug}: could not match section headings to their ids.')
    return [Section(slug=policy.slug, version=policy.version, title=policy.title, owner=policy.owner, anchor=anchor,
                    heading=heading, body=body.strip(), policy_id=policy.pk)
            for anchor, heading, body in zip(anchors, headings, bodies)]


def _flatten(tokens):
    for token in tokens:
        yield token
        yield from _flatten(token['children'])


def extension_installable():
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT FROM pg_available_extensions WHERE name = 'vector')")
        return cursor.fetchone()[0]


def is_available():
    """True when the database has the vector extension and a built index, and an embedding model is configured."""
    if not settings.AZURE_OPENAI_ENDPOINT:
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector') "
                       "AND to_regclass('policy_section') IS NOT NULL")
        return cursor.fetchone()[0]


def embed(texts):
    """Embeddings for a list of texts, from the Azure OpenAI deployment, signed in with the app's managed identity."""
    url = (f'{settings.AZURE_OPENAI_ENDPOINT.rstrip("/")}/openai/deployments/'
           f'{settings.POLICY_EMBEDDING_DEPLOYMENT}/embeddings?api-version=2024-10-21')
    headers = {'Authorization': f"Bearer {managed_identity.token('https://cognitiveservices.azure.com')}"}
    vectors = []
    for start in range(0, len(texts), BATCH):
        response = httpx.post(url, timeout=30, headers=headers,
                              json={'input': texts[start:start + BATCH], 'dimensions': DIMENSIONS})
        response.raise_for_status()
        vectors.extend(item['embedding'] for item in sorted(response.json()['data'], key=lambda d: d['index']))
    return vectors


def _vector(values):
    return '[' + ','.join(f'{v:.7g}' for v in values) + ']'


def build_index():
    """Creates the policy_section table if needed and replaces its rows with every published policy's sections."""
    with connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS policy_section (
                id bigserial PRIMARY KEY,
                policy_id integer NOT NULL REFERENCES policies_policy (id) ON DELETE CASCADE,
                anchor text NOT NULL,
                heading text NOT NULL,
                body text NOT NULL,
                embedding vector({DIMENSIONS}) NOT NULL,
                UNIQUE (policy_id, anchor)
            )""")
        cursor.execute('CREATE INDEX IF NOT EXISTS policy_section_embedding_idx '
                       'ON policy_section USING hnsw (embedding vector_cosine_ops)')
    sections = [section for policy in Policy.objects.published() for section in split_sections(policy)]
    vectors = embed([section.text_to_embed() for section in sections])
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('DELETE FROM policy_section')
        cursor.executemany(
            'INSERT INTO policy_section (policy_id, anchor, heading, body, embedding) VALUES (%s, %s, %s, %s, %s::vector)',
            [(s.policy_id, s.anchor, s.heading, s.body, _vector(v)) for s, v in zip(sections, vectors)],
        )
    return len(sections)


def search(question, state, limit=5):
    """The published policy sections nearest to the question that apply in the given state, nearest first."""
    [vector] = embed([question])
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.slug, p.version, p.title, p.owner, s.anchor, s.heading, s.body
            FROM policy_section s
            JOIN policies_policy p ON p.id = s.policy_id
            WHERE p.status = 'published' AND (p.applies_to_states = '' OR p.applies_to_states ~ %s)
            ORDER BY s.embedding <=> %s::vector
            LIMIT %s
            """,
            [rf'(^|,){re.escape(state)}(,|$)', _vector(vector), limit],
        )
        return [Section(*row) for row in cursor.fetchall()]
