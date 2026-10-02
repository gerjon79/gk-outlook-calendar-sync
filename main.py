import os
import secrets

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from calendar_sync_helper.routers.router_v1 import router as router_v1

API_KEY_HEADER_NAME = "X-API-Key"
UNPROTECTED_PATHS = {"/health"}


def create_app():
    app = FastAPI()

    # Optional protection: if the API_KEY environment variable is set, every request (except the health check) must
    # provide it in the X-API-Key header. Without API_KEY, the service is open (backwards-compatible behavior).
    api_key = os.getenv("API_KEY")
    if api_key:
        @app.middleware("http")
        async def verify_api_key(request: Request, call_next):
            if request.url.path not in UNPROTECTED_PATHS:
                provided_key = request.headers.get(API_KEY_HEADER_NAME, "")
                if not secrets.compare_digest(provided_key.encode(), api_key.encode()):
                    return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
            return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(router_v1)
    app.include_router(router_v1, prefix="/v1")

    return app


app = create_app()

if __name__ == "__main__":  # For when running main.py in the debugger of an IDE
    uvicorn.run(app, host="0.0.0.0", port=8000)
