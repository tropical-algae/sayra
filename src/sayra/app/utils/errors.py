from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from loguru import logger
from starlette.responses import JSONResponse

from sayra.common.datetime import utc_now
from sayra.core.exceptions import SayraError


def _body(code: str, message: str, details: object | None = None) -> dict:
    return {
        "error": {"code": code, "message": message, "details": details},
        "timestamp": utc_now().isoformat(),
    }


def add_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SayraError)
    async def sayra_error_handler(_request: Request, exc: SayraError):
        return JSONResponse(
            status_code=exc.status_code, content=_body(exc.code, str(exc))
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        errors = exc.errors()
        for error in errors:
            if "ctx" in error:
                error["ctx"] = {key: str(value) for key, value in error["ctx"].items()}
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Invalid request", errors),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled request error: {}", exc)
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "Internal server error"),
        )
