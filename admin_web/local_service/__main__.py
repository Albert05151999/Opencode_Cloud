"""Loopback-only local companion entry point."""

from .configuration import load
import uvicorn
from .runtime import LocalServer
from .server import create_local_app

if __name__ == "__main__":
    LocalServer(
        uvicorn.Config(
            create_local_app(),
            host="127.0.0.1",
            port=load()["port"],
            timeout_graceful_shutdown=5,
        )
    ).run()
