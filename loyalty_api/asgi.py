"""Local entry point: uv run uvicorn asgi:app --reload"""

from loyalty.main import create_app
from loyalty.settings import Settings

app = create_app(Settings.from_env())
