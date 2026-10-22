"""Connections to the store operations database and to Snowflake, configured from .env."""

import os
from pathlib import Path

import psycopg
import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


def connect_postgres():
    return psycopg.connect(
        autocommit=True,
        dbname=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
        sslmode=os.environ.get('POSTGRES_SSLMODE', 'prefer'),
    )


def connect_snowflake():
    return snowflake.connector.connect(
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        user=os.environ['SNOWFLAKE_USER'],
        role=os.environ['SNOWFLAKE_ROLE'],
        warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
        database=os.environ['SNOWFLAKE_DATABASE'],
        schema='RAW',
        authenticator='SNOWFLAKE_JWT',
        private_key_file=os.environ['SNOWFLAKE_PRIVATE_KEY_PATH'],
    )
