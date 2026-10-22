"""The Dagster definitions load, and every dbt source has a loader asset upstream of it."""

from dagster import AssetKey, Definitions

from orchestration.definitions import ENDPOINTS, STORE_TABLES, daily_schedule, defs


def test_definitions_load():
    Definitions.validate_loadable(defs)
    assert defs.resolve_job_def('daily_pipeline')


def test_every_raw_table_has_a_loader():
    graph = defs.resolve_asset_graph()
    loaded = set(STORE_TABLES) | set(ENDPOINTS)
    # Every asset that dbt reads but doesn't build is a raw table, and a loader must build it.
    dbt_inputs = {dep for key in graph.get_all_asset_keys() if graph.get(key).is_materializable
                  for dep in graph.get(key).parent_keys}
    assert dbt_inputs - set(graph.get_all_asset_keys()) == set()
    assert loaded <= set(graph.get_all_asset_keys())
    assert AssetKey(['store_ops', 'sale_lines']) in loaded


def test_store_tables_map_to_postgres_names():
    assert STORE_TABLES[AssetKey(['store_ops', 'sale_lines'])] == 'sales_saleline'
    assert STORE_TABLES[AssetKey(['store_ops', 'animal_caretakers'])] == 'inventory_animal_caretakers'


def test_a_dbt_model_depends_on_its_raw_tables():
    graph = defs.resolve_asset_graph()
    staging = AssetKey(['staging', 'stg_store_ops__sale_lines'])
    assert AssetKey(['store_ops', 'sale_lines']) in graph.get(staging).parent_keys


def test_runs_daily_in_utc():
    assert daily_schedule.cron_schedule == '0 9 * * *'
    assert daily_schedule.execution_timezone == 'UTC'


def test_dbt_assets_are_grouped_by_layer():
    graph = defs.resolve_asset_graph()
    assert graph.get(AssetKey(['staging', 'stg_store_ops__sale_lines'])).group_name == 'staging'
    assert graph.get(AssetKey(['marts', 'fct_sales'])).group_name == 'marts'
    assert graph.get(AssetKey(['store_ops', 'sale_lines'])).group_name == 'store_ops'
