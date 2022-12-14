from typing import Callable

import aioredis
from boto3 import resource
from aioredis import Redis
from fastapi.concurrency import run_in_threadpool

from config.settings import Settings

settings = Settings()


async def func_asyncio(func: Callable, **kwargs):
    return await run_in_threadpool(func, **kwargs)


async def get_redis_pool() -> Redis:
    return await aioredis.from_url(
        f'redis://{settings.redis.redis_host}:{settings.redis.redis_port}',
        password=f'{settings.redis.redis_password}',
        encoding='utf-8',
        decode_responses=True
    )


async def get_dynamo():
    return await func_asyncio(
        func=resource,
        service_name='dynamodb',
        aws_access_key_id=settings.boto3.aws_access_key_id,
        aws_secret_access_key=settings.boto3.aws_secret_access_key,
        region_name=settings.boto3.region_name
    )


async def get_table(dynamo):
    return await func_asyncio(dynamo.Table, name=settings.dynamo.table_name)
