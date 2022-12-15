import logging
from functools import wraps
from fastapi.logger import logger


gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)


def log_request(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info(f"[{func.__name__}] {kwargs}")
        return await func(*args, **kwargs)

    return wrapper
