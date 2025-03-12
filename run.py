# run.py
import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dialer_app.routes import router as routes_router
from fastapi.middleware.cors import CORSMiddleware
from pyngrok import ngrok
from dialer_app.config import Config
import logging
from logging.config import dictConfig

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(levelname)s: %(message)s",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
            "filters": []
        },
    },
}

class SocketIOFilter(logging.Filter):
    def filter(self, record):
        return "socket.io" not in record.getMessage()

logging_config["loggers"]["uvicorn.access"]["filters"] = ["socket_io_filter"]
logging_config["filters"] = {
    "socket_io_filter": {
        "()": SocketIOFilter
    }
}

dictConfig(logging_config)
logging.basicConfig(level=logging.INFO)

def create_app():
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True
    )
    app.include_router(routes_router)
    app.mount("/static", StaticFiles(directory="dialer_app/static"), name="static")
    return app

def start_ngrok(app_port: int):
    if Config.NGROK_ENABLED:
        auth_token = Config.NGROK_AUTH_TOKEN
        if auth_token:
            ngrok.set_auth_token(auth_token)
        public_url = ngrok.connect(app_port, bind_tls=True).public_url
        os.environ["NGROK_URL"] = public_url
        print(f"[NGROK] Tunnel running at {public_url} -> http://127.0.0.1:{app_port}")
    else:
        print("[NGROK] Not enabled.")

app = create_app()

if __name__ == "__main__":
    app_port = 5000
    start_ngrok(app_port)
    uvicorn.run("run:app", host="0.0.0.0", port=app_port, reload=True)
