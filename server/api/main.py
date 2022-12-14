import json
import logging
import time
import uuid
from functools import wraps
from typing import Any

from boto3.dynamodb import conditions
from fastapi import FastAPI, status, Request
from fastapi.logger import logger
from fastapi.responses import JSONResponse
from pydantic.json import pydantic_encoder

from config.db import *
from config.models import *
from config.settings import Settings


app = FastAPI(
    title="Pick Chat",
    version="0.1.0",
    description="픽스튜디오 채팅 플랫폼",
    contact={
        "name": "Heyho",
        "email": "nerolizm@gmail.com"
    }
)
settings = Settings()
redis: Union[Redis, None] = None
table: Any = None

gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)

THOUSAND_TIMES: int = 1000
MAX_MESSAGE_COUNT: int = 300


def log_request(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info(f"[{func.__name__}] {kwargs}")
        return await func(*args, **kwargs)

    return wrapper


@app.on_event('startup')
async def startup():
    global redis, table
    redis = await get_redis_pool()
    table = await get_table(await get_dynamo())


@app.on_event('shutdown')
async def shutdown():
    await redis.close()


@app.middleware("http")
async def except_logging_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.info(e)
        return JSONResponse({"message": e}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


async def get_last_message(channel_id: str) -> dict:
    query = {
        "IndexName": "channel_id-created_at-index",
        "KeyConditionExpression": conditions.Key('channel_id').eq(channel_id),
        "ScanIndexForward": False,
        "Limit": 1
    }
    result = await func_asyncio(table.query, **query)
    return result['Items'][0] if result['Count'] > 0 else {}


async def get_last_read_time(service: Service, user_id: str, channel_id: str) -> int:
    return int(await redis.hget(f'channels#{channel_id}#status', f'{service}#{user_id}#read'))


async def get_unread_message_count(service: Service, user_id: str, channel_id: str) -> int:
    query = {
        "IndexName": "channel_id-created_at-index",
        "KeyConditionExpression": conditions.Key('channel_id').eq(channel_id) &
                                  conditions.Key('created_at').gte(await get_last_read_time(service, user_id, channel_id))
    }
    result = await func_asyncio(table.query, **query)
    return result['Count']


async def member_exists(service: Service, user_id: str) -> bool:
    return await redis.exists(f'users#{service}#{user_id}')


async def channel_joined(service: Service, user_id: str, channel_id: str) -> bool:
    return True if await redis.hget(f'channels#{channel_id}#members', f'{service}#{user_id}') == 'joined' else False


async def marked_as_read(service: Service, user_id: str, channel_id: str, read_time: int = None) -> None:
    await redis.hset(
        name=f'channels#{channel_id}#status',
        key=f'{service}#{user_id}#read',
        value=read_time or int(time.time() * THOUSAND_TIMES)
    )


@app.get("/", status_code=200, include_in_schema=False)
async def health_check():
    return


@app.put("/users/{service}/{user_id}", response_model=User, tags=["User"])
@log_request
async def upsert_user(service: Service, user_id: str, request: UserRequest):
    """Register/modify user"""
    user = User(
        service=service,
        user_id=user_id,
        nickname=request.nickname,
        source=json.dumps(request.source, default=pydantic_encoder, ensure_ascii=False),
        meta=json.dumps(request.meta, default=pydantic_encoder, ensure_ascii=False)
    )
    await redis.hset(f'users#{service}#{user_id}', mapping=user.dict())

    return user


@app.delete("/users/{service}/{user_id}", tags=["User"])
@log_request
async def delete_user(service: Service, user_id: str):
    """Delete user"""
    if await redis.delete(f'users#{service}#{user_id}'):
        return JSONResponse({'message': 'User deleted successfully'}, status.HTTP_200_OK)


@app.post("/users/{service}/{user_id}/tokens/{token_type}", response_model=TokenResponse, tags=["Token"])
@log_request
async def add_token(service: Service, user_id: str, token_type: TokenType, request: TokenRequest):
    """Add push token"""
    user = await redis.hgetall(f'users#{service}#{user_id}')
    await redis.sadd(f'users#{service}#{user_id}#{token_type}', request.push_token)

    return TokenResponse(
        token=request.push_token,
        token_type=token_type,
        user=User(**user)
    )


@app.put("/users/{service}/{user_id}/tokens/{token_type}", response_model=TokenRemoveResponse, tags=["Token"])
@log_request
async def remove_token(service: Service, user_id: str, token_type: TokenType, request: TokenRequest):
    """Remove specific token"""
    await redis.srem(f'users#{service}#{user_id}#{token_type}', request.push_token)

    return TokenRemoveResponse(
        tokens=await redis.smembers(f'users#{service}#{user_id}#{token_type}'),
        token_type=token_type,
        user=User(**await redis.hgetall(f'users#{service}#{user_id}'))
    )


@app.delete("/users/{service}/{user_id}/tokens/{token_type}", tags=["Token"])
@log_request
async def delete_tokens(service: Service, user_id: str, token_type: TokenType):
    """Delete tokens by type"""
    if await redis.delete(f'users#{service}#{user_id}#{token_type}'):
        return JSONResponse({'message': 'Token deleted successfully'}, status.HTTP_200_OK)


@app.get("/channels/{service}/{user_id}", response_model=ChannelList, tags=["Channel"])
@log_request
async def list_channels(service: Service, user_id: str):
    """List channels"""
    async def get_members(users: dict) -> tuple:
        member_list = []
        joined_count = 0
        for user, state in users.items():
            member_list.append(MemberWithState(**await redis.hgetall(f'users#{user}'), state=state))
            if state == 'joined':
                joined_count += 1
        return member_list, len(users), joined_count

    channels = []
    channel_list = await redis.smembers(f'users#{service}#{user_id}#channels')

    for channel_id in channel_list:
        [members, member_count, joined_member_count] = await get_members(
            await redis.hgetall(f'channels#{channel_id}#members')
        )
        channels.append(ChannelListResponse(
            **await redis.hgetall(f'channels#{channel_id}'),
            member_count=member_count,
            joined_member_count=joined_member_count,
            members=members,
            unread_message_count=await get_unread_message_count(service, user_id, channel_id),
            last_message=await get_last_message(channel_id)
        ))

    return ChannelList(channels=channels)


@app.post("/channels", response_model=ChannelResponse, tags=["Channel"])
@log_request
async def create_channel(request: ChannelRequest):
    """Create channel"""
    async def channel_type() -> ChannelType:
        return ChannelType.GROUP if len(request.members) > 2 else ChannelType.ONE_ON_ONE

    timestamp = int(time.time() * THOUSAND_TIMES)
    channel_id = str(uuid.uuid4())
    channel_type = await channel_type()

    for member in request.members:
        if not await member_exists(member.service, member.user_id):
            return JSONResponse({'message': f"[{member.service}] '{member.user_id}' is not exists"}, status.HTTP_400_BAD_REQUEST)

    for member in request.members:
        await redis.sadd(f'users#{member.service}#{member.user_id}#channels', channel_id)
        await redis.hset(f'channels#{channel_id}#members', f'{member.service}#{member.user_id}', 'joined')
        await redis.hset(f'channels#{channel_id}#status', f'{member.service}#{member.user_id}#read', 0)

    channel = Channel(
        channel=channel_id,
        type=channel_type,
        created_at=timestamp
    )
    await redis.hset(f'channels#{channel_id}', mapping=channel.dict())

    return ChannelResponse(channel=channel_id, type=channel_type)


@app.put("/channels/{channel_id}/leave", tags=["Channel"])
@log_request
async def leave_channel(channel_id: str, request: Member):
    """Leave the channel"""
    if not await member_exists(request.service, request.user_id):
        return JSONResponse({'message': f"[{request.service}] '{request.user_id}' is not exists"}, status.HTTP_400_BAD_REQUEST)

    if not await channel_joined(request.service, request.user_id, channel_id):
        return JSONResponse({'message': f"[{request.service}] '{request.user_id}' is not joined this channel"}, status.HTTP_400_BAD_REQUEST)

    await redis.hset(f'channels#{channel_id}#members', f'{request.service}#{request.user_id}', 'left')
    await redis.srem(f'users#{request.service}#{request.user_id}#channels', channel_id)

    return JSONResponse({'message': 'Channel left successfully'}, status.HTTP_200_OK)


@app.get("/messages/{service}/{user_id}/{channel_id}", response_model=MessageListResponse, tags=["Message"])
@log_request
async def list_messages(service: Service, user_id: str, channel_id: str):
    """List messages"""
    async def count() -> int:
        message_count = await get_unread_message_count(service, user_id, channel_id)
        return message_count + MAX_MESSAGE_COUNT

    async def get_messages() -> dict:
        query = {
            "IndexName": "channel_id-created_at-index",
            "KeyConditionExpression": conditions.Key('channel_id').eq(channel_id),
            "Limit": await count()
        }
        result = await func_asyncio(table.query, **query)
        return result['Items'] if result['Count'] > 0 else {}

    return MessageListResponse(
        last_read_time=await get_last_read_time(service, user_id, channel_id),
        messages=[MessageResponse(**message) for message in await get_messages()]
    )


@app.post("/messages", response_model=MessageResponse, tags=["Message"])
@log_request
async def send_message(request: Message):
    """Send a message"""
    async def push(members):
        pass

    async def broadcast():
        message_response = MessageResponse(
            message_id=str(uuid.uuid4()),
            view_type=request.view_type,
            view=request.view,
            created_at=request.date,
            created_by=User(**await redis.hgetall(f"users#{request.service}#{request.user_id}"))
        )

        await func_asyncio(table.put_item, Item={'channel_id': request.channel_id, **message_response.dict()})
        await marked_as_read(request.service, request.user_id, request.channel_id, request.date)
        await push(await redis.hkeys(f'channels#{request.channel_id}#members'))

        return message_response

    if not await member_exists(request.service, request.user_id):
        return JSONResponse({'message': f"[{request.service}] '{request.user_id}' is not exists"}, status.HTTP_400_BAD_REQUEST)

    return await broadcast()


@app.put("/messages/{channel_id}/read", tags=["Message"])
@log_request
async def read_message(channel_id: str, request: MessageRequest):
    """Update message as read"""
    if not await member_exists(request.service, request.user_id):
        return JSONResponse({'message': f"[{request.service}] '{request.user_id}' is not exists"}, status.HTTP_400_BAD_REQUEST)

    await marked_as_read(request.service, request.user_id, channel_id)

    return JSONResponse({'message': 'Marked as read successfully'}, status.HTTP_200_OK)
