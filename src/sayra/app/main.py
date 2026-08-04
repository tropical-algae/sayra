from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sayra.app.api.routers import router as api_router
from sayra.app.container import AppContainer
from sayra.app.utils.errors import add_exception_handlers
from sayra.common.config import settings
from sayra.common.logging import intercept_std_logging


def create_app(container: AppContainer | None = None) -> FastAPI:
    app_container = container or AppContainer(settings)
    config = app_container.config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = app_container
        try:
            await app_container.startup()
            yield
        finally:
            await app_container.shutdown()

    application = FastAPI(
        title=config.PROJECT_NAME,
        debug=config.DEBUG,
        version=config.VERSION,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=config.API_PREFIX)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    add_exception_handlers(application)
    return application


app = create_app()


def run() -> None:
    intercept_std_logging()
    uvicorn.run(
        "sayra.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        access_log=True,
    )


if __name__ == "__main__":
    run()
