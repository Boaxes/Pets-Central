"""The daily pipeline as Dagster assets: both loaders, then every dbt model and test, on one schedule.

Each raw table is its own asset, keyed the way dbt names its sources (store_ops/sales, loyalty/members...), so the
lineage shows exactly which raw tables each dbt model reads. The loader assets are built from dbt's own list of
sources, so there is no second list to keep in step.

    uv run --project orchestration dagster dev      (from the repository root)
"""

import json
import os
from pathlib import Path

from dagster import (AssetExecutionContext, AssetKey, AssetSelection, AssetSpec, DefaultScheduleStatus, Definitions,
                     MaterializeResult, ScheduleDefinition, define_asset_job, multi_asset)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from pipeline import load_loyalty, load_store_ops

ROOT = Path(__file__).resolve().parent.parent

dbt_project = DbtProject(project_dir=ROOT / 'transform', profiles_dir=ROOT / 'transform')
dbt_project.prepare_if_dev()  # `dagster dev` parses the dbt project; images parse it at build time.

SOURCES = [s for s in json.loads(dbt_project.manifest_path.read_text())['sources'].values()]


# The store operations loader ------------------------------------------------------------------------------------

# Postgres table for each raw table: STORE_OPS__SALES_SALELINE is loaded from sales_saleline.
STORE_TABLES = {
    AssetKey(['store_ops', s['name']]): s['identifier'].removeprefix(load_store_ops.TARGET_PREFIX).lower()
    for s in SOURCES if s['source_name'] == 'store_ops'
}


@multi_asset(
    name='store_ops_loader',
    specs=[AssetSpec(key, group_name='store_ops', kinds={'snowflake'},
                     description=f"RAW copy of the store app's Postgres table {table}, loaded by "
                                 'pipeline/load_store_ops.py.')
           for key, table in STORE_TABLES.items()],
    can_subset=True,
)
def store_ops_loader(context: AssetExecutionContext):
    """New and changed rows from the store app's Postgres database, per each table's strategy."""
    tables = {STORE_TABLES[key]: key for key in context.selected_asset_keys}
    for table, rows in load_store_ops.run(sorted(tables)).items():
        yield MaterializeResult(asset_key=tables[table], metadata={
            'rows_loaded': rows, 'strategy': load_store_ops.STRATEGIES.get(table, load_store_ops.FULL)})


# The loyalty platform loader ------------------------------------------------------------------------------------

ENDPOINTS = {AssetKey(['loyalty', e.name]): e for e in load_loyalty.ENDPOINTS}
assert set(ENDPOINTS) == {AssetKey(['loyalty', s['name']]) for s in SOURCES if s['source_name'] == 'loyalty'}, \
    "The loyalty loader's endpoints and dbt's loyalty sources must match."


@multi_asset(
    name='loyalty_loader',
    specs=[AssetSpec(key, group_name='loyalty', kinds={'snowflake'},
                     description=f"RAW copy of the loyalty vendor's {e.path}, pulled from their API as raw JSON by "
                                 'pipeline/load_loyalty.py. The API belongs to the vendor; Pets Central only calls it.')
           for key, e in ENDPOINTS.items()],
    can_subset=True,
)
def loyalty_loader(context: AssetExecutionContext):
    """Pulls what the vendor's API received since the last pull, with an hour of overlap for late writes."""
    endpoints = {ENDPOINTS[key].name: key for key in context.selected_asset_keys}
    counts = load_loyalty.run([ENDPOINTS[key] for key in context.selected_asset_keys])
    for name, records in counts.items():
        yield MaterializeResult(asset_key=endpoints[name], metadata={'records_loaded': records})


# dbt --------------------------------------------------------------------------------------------------------------

class LayerGroups(DagsterDbtTranslator):
    """Groups dbt's assets by layer, the folder they live in: staging, intermediate, marts, evaluation."""

    def get_asset_spec(self, manifest, unique_id, project):
        spec = super().get_asset_spec(manifest, unique_id, project)
        node = manifest['nodes'].get(unique_id) or manifest['sources'][unique_id]
        if node['resource_type'] == 'seed':
            return spec.replace_attributes(group_name='evaluation')  # The truth files only the evaluation uses.
        if node['resource_type'] == 'model':
            return spec.replace_attributes(group_name=node['fqn'][1])
        return spec


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=LayerGroups())
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    """Every seed, model and test. A failed test stops the models downstream of it."""
    yield from dbt.cli(['build'], context=context).stream()


# One job, once a day ------------------------------------------------------------------------------------------------

daily_pipeline = define_asset_job('daily_pipeline', selection=AssetSelection.all(),
                                  description='Load both sources into RAW, then build and test every dbt model.')

daily_schedule = ScheduleDefinition(
    job=daily_pipeline,
    # 09:00 UTC is after every US store has closed. PIPELINE_CRON moves it, e.g. to run within the hour.
    cron_schedule=os.environ.get('PIPELINE_CRON', '0 9 * * *'),
    execution_timezone='UTC',
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[store_ops_loader, loyalty_loader, dbt_models],
    jobs=[daily_pipeline],
    schedules=[daily_schedule],
    resources={'dbt': DbtCliResource(project_dir=dbt_project)},
)
