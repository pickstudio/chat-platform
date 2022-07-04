import asyncio
import functools
from typing import Callable, Awaitable

import aioredis
from boto3 import resource, client
from aioredis import Redis

from app.settings import Settings

settings = Settings()


async def func_asyncio(func: Callable, **kwargs) -> Awaitable:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, **kwargs))


async def get_redis_pool() -> Redis:
    return await aioredis.from_url(
        f'redis://{settings.redis.redis_host}',
        password=f'{settings.redis.redis_password}',
        encoding='utf-8',
        decode_responses=True
    )


async def get_dynamo_pool():
    return await func_asyncio(
        func=resource,
        service_name='dynamodb',
        aws_access_key_id=settings.boto3.aws_access_key_id,
        aws_secret_access_key=settings.boto3.aws_secret_access_key,
        region_name=settings.boto3.region_name
    )


def put_item(dynamodb: client, table: str) -> Callable:
    return dynamodb.Table(table).put_item


