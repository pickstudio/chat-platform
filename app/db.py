import asyncio
import functools

import aioredis
import boto3
from aioredis import Redis

from app.settings import Settings

settings = Settings()


async def get_resource(**kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(boto3.resource, **kwargs))


async def put_items(table, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(table.put_item, **kwargs))


async def get_redis_pool() -> Redis:
    return await aioredis.from_url(
        f'redis://{settings.redis.redis_host}',
        password=f'{settings.redis.redis_password}',
        encoding='utf-8',
        decode_responses=True
    )


async def get_dynamo_pool():
    return await get_resource(
        service_name='dynamodb',
        aws_access_key_id=settings.boto3.aws_access_key_id,
        aws_secret_access_key=settings.boto3.aws_secret_access_key,
        region_name=settings.boto3.region_name
    )
