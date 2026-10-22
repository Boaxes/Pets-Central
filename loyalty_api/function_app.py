"""Azure Functions entry point. One HTTP function receives every request and FastAPI routes it."""

import azure.functions as func

from loyalty.main import create_app
from loyalty.settings import Settings

app = func.AsgiFunctionApp(app=create_app(Settings.from_env()), http_auth_level=func.AuthLevel.ANONYMOUS)
