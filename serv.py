import os

from sanic import Sanic
from sanic.response import json

from config.load_env import load_env


load_env()

app = Sanic("Aix-DB-Copy")


@app.get("/")
async def index(request):
    return json(
        {
            "name": "Aix-DB-Copy",
            "status": "running",
            "environment": os.getenv("APP_ENV"),
        }
    )


@app.get("/health")
async def health(request):
    return json({"healthy": True})


def get_server_config() -> dict:
    return {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "8088")),
        "single_process": True,
        "auto_reload": False,
    }


if __name__ == "__main__":
    server_config = get_server_config()
    app.run(**server_config)