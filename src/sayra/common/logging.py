import logging
import sys
from pathlib import Path
from types import FrameType

from loguru import logger

from sayra.common.config import Settings, settings


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(config: Settings = settings) -> None:
    """Configure Loguru explicitly during process startup, without import side effects."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=config.LOG_LEVEL,
        colorize=True,
        enqueue=True,
        format=(
            "<green>{time:YYYYMMDD HH:mm:ss}</green> | {process.name} | "
            "{thread.name} | <cyan>{module}</cyan>.<cyan>{function}</cyan>:"
            "<cyan>{line}</cyan> | <level>{level}</level>: <level>{message}</level>"
        ),
    )
    if config.LOG_FILE_OUTPUT:
        log_path = Path(config.LOG_ROOT) / f"{config.PROJECT_NAME}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path,
            format=(
                "{time:YYYYMMDD HH:mm:ss} - {process.name} | {thread.name} | "
                "{module}.{function}:{line} - {level} - {message}"
            ),
            encoding=config.LOG_FILE_ENCODING,
            retention="12 week",
            rotation="1 week",
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )


def intercept_std_logging(config: Settings = settings) -> None:
    configure_logging(config)
    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=config.LOG_LEVEL, force=True)
    logger_names = ["uvicorn.asgi", "uvicorn.access", "uvicorn"]
    if config.DEBUG:
        logger_names.extend(["sqlalchemy.engine", "sqlalchemy.engine.Engine"])
    for logger_name in logger_names:
        std_logger = logging.getLogger(logger_name)
        std_logger.handlers = [handler]
        std_logger.setLevel(config.LOG_LEVEL)
