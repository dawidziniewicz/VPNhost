import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=config.PANEL_HOST, port=config.PANEL_PORT,
                proxy_headers=False, access_log=False, log_level="info")
