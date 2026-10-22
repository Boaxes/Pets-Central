# The store app: Django served by gunicorn, static files by WhiteNoise. The same image runs the `manage` job
# (migrations, data generation, the policy index) with a different command.

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# Fail the build, not a 40-minute data load, if a file the generator needs was left out of the image.
RUN test -f loyalty_api/loyalty/schema.sql
# Settings read these at import; collectstatic needs no real values.
RUN DJANGO_SECRET_KEY=build POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app && mkdir -p data && chown app data
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
