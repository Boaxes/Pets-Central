# Dagster: the loaders, the dbt project and the definitions in one image. Build from the repository root:
#     docker build -f orchestration/Dockerfile .
# One container runs the webserver (the default command), another the daemon: dagster-daemon run.

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/orchestration/.venv/bin:$PATH" DAGSTER_HOME=/app/dagster_home PETS_EVALUATION=false
WORKDIR /app

COPY orchestration/pyproject.toml orchestration/uv.lock orchestration/
RUN uv sync --frozen --no-dev --no-install-project --project orchestration

COPY pipeline/ pipeline/
COPY transform/ transform/
COPY orchestration/ orchestration/

# dbt's packages and manifest are built into the image, so Dagster can read the project without running dbt first.
# The profile reads these at parse time; parsing doesn't connect, so placeholders do.
RUN cd transform && export SNOWFLAKE_ACCOUNT=build SNOWFLAKE_DBT_USER=build SNOWFLAKE_DBT_ROLE=build \
        SNOWFLAKE_DBT_PRIVATE_KEY_PATH=build SNOWFLAKE_WAREHOUSE=build SNOWFLAKE_DATABASE=build \
    && dbt deps && dbt parse

COPY orchestration/dagster.yaml dagster_home/dagster.yaml
RUN useradd --create-home --uid 1000 app && mkdir -p data && chown -R app data dagster_home transform
USER app

EXPOSE 3000
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "orchestration.definitions"]
