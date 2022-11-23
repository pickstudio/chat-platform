import asyncio
import json
import logging
import time
import uuid
from functools import wraps
from typing import Any

from aioredis.client import PubSub
from boto3.dynamodb import conditions
from fastapi import FastAPI, status, Depends, Request
from fastapi.logger import logger
from fastapi.responses import JSONResponse
from pydantic.json import pydantic_encoder
from starlette.websockets import WebSocketDisconnect

from .db import *
from .models import *
from .settings import Settings


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
        return JSONResponse({'message': f'User deleted successfully'}, status.HTTP_200_OK)


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


@app.delete("/users/{service}/{user_id}/tokens/{token_type}", tags=["Token"])
@log_request
async def delete_tokens(service: Service, user_id: str, token_type: TokenType):
    """Delete token by type"""
    await redis.delete(f'users#{service}#{user_id}#{token_type}')


@app.put("/users/{service}/{user_id}/tokens/{token_type}/", response_model=TokenRemoveResponse, tags=["Token"])
@log_request
async def remove_token(service: Service, user_id: str, token_type: TokenType, request: TokenRequest):
    """Remove specific token"""
    await redis.srem(f'users#{service}#{user_id}#{token_type}', request.push_token)

    return TokenRemoveResponse(
        tokens=await redis.smembers(f'users#{service}#{user_id}#{token_type}'),
        token_type=token_type,
        user=User(**await redis.hgetall(f'users#{service}#{user_id}'))
    )


@app.post("/channels", response_model=ChannelResponse, tags=["Channel"])
@log_request
async def create_channel(request: ChannelRequest):
    """Create channel"""
    timestamp = int(time.time() * THOUSAND_TIMES)
    channel_id = str(uuid.uuid4())
    users = []

    for member in request.members:
        users.append(await redis.hgetall(f'users#{member.service}#{member.user_id}'))
        await redis.sadd(f'users#{member.service}#{member.user_id}#channels', channel_id)
        await redis.hset(f'channels#{channel_id}#members', f'{member.service}#{member.user_id}', 'joined')
        await redis.hset(f'channels#{channel_id}#status', f'{member.service}#{member.user_id}#read', 0)

    channel = Channel(
        channel=channel_id,
        type=request.type,
        created_at=timestamp
    )

    await redis.hset(f'channels#{channel_id}', mapping=channel.dict())

    return ChannelResponse(channel=channel_id)


async def get_last_message(channel_id: str) -> dict:
    query = {
        "IndexName": "channel_id-created_at-index",
        "KeyConditionExpression": conditions.Key('channel_id').eq(channel_id),
        "ScanIndexForward": False,
        "Limit": 1
    }
    result = await func_asyncio(table.query, **query)
    return result['Items'][0] if result['Count'] > 0 else {}


async def get_last_read_time(service: str, user_id: str, channel_id: str) -> int:
    return int(await redis.hget(f'channels#{channel_id}#status', f'{service}#{user_id}#read'))


async def get_unread_message_count(service: str, user_id: str, channel_id: str) -> int:
    query = {
        "IndexName": "channel_id-created_at-index",
        "KeyConditionExpression": conditions.Key('channel_id').eq(channel_id) &
                                  conditions.Key('created_at').gte(await get_last_read_time(service, user_id, channel_id))
    }
    result = await func_asyncio(table.query, **query)
    return result['Count']


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


@app.put("/channels/{channel}/join", tags=["Channel"], deprecated=True)
@log_request
async def join_channel(channel: str, request: Member):
    """Join the channel"""
    pass


@app.put("/channels/{channel}/leave", tags=["Channel"])
@log_request
async def leave_channel(channel: str, request: Member):
    """Leave the channel"""
    await redis.hset(f'channels#{channel}#members', f'{request.service}#{request.user_id}', 'left')
    await redis.srem(f'users#{request.service}#{request.user_id}#channels', channel)


@app.get("/messages/{service}/{user_id}/{channel}", response_model=MessageListResponse, tags=["Message"])
@log_request
async def list_messages(service: Service, user_id: str, channel: str):
    """List messages"""
    async def count() -> int:
        message_count = await get_unread_message_count(service, user_id, channel)
        return message_count if message_count > 0 else MAX_MESSAGE_COUNT

    async def get_messages() -> dict:
        query = {
            "IndexName": "channel_id-created_at-index",
            "KeyConditionExpression": conditions.Key('channel_id').eq(channel),
            "Limit": await count()
        }
        result = await func_asyncio(table.query, **query)
        return result['Items'] if result['Count'] > 0 else {}

    return MessageListResponse(
        last_read_time=await get_last_read_time(service, user_id, channel),
        messages=[MessageResponse(**message) for message in await get_messages()]
    )


@app.get("/chat", tags=["chat"], include_in_schema=False)
async def get():
    from starlette.responses import HTMLResponse
    from app.html import html
    return HTMLResponse(html)


@app.websocket("/channels/{channel}/{service}/{user_id}")
async def websocket_endpoint(request: ChatRequest = Depends()):
    await request.ws.accept()
    await connection(request)


async def connection(request: ChatRequest):
    async def client_handler(ws: WebSocket):
        try:
            while True:
                message = await ws.receive_json()
                if message:
                    await broadcast(request.channel, message=message)
        except WebSocketDisconnect:
            await leave(request)

    async def pubsub_handler(ws: WebSocket):
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await ws.send_text(message.get('data'))
        except Exception as exc:
            logger.info(f'{pubsub_handler.__name__} : {exc}')

    await enter(request)

    pubsub: PubSub = redis.pubsub()
    await pubsub.subscribe(request.channel)

    pubsub_task = pubsub_handler(request.ws)
    client_task = client_handler(request.ws)

    done, pending = await asyncio.wait(
        [pubsub_task, client_task], return_when=asyncio.FIRST_EXCEPTION,
    )

    for task in pending:
        logger.info(f'Canceling task: {task}')
        task.cancel()


async def enter(request: ChatRequest):
    await redis.hset(
        f'channels#{request.channel}#status',
        f'{request.member.service}#{request.member.user_id}#read',
        int(time.time() * THOUSAND_TIMES)
    )


async def leave(request: ChatRequest):
    await redis.hset(
        f'channels#{request.channel}#status',
        f'{request.member.service}#{request.member.user_id}#read',
        int(time.time() * THOUSAND_TIMES)
    )


@log_request
async def broadcast(channel: str, message: dict):
    async def typed(msg):
        if msg['view_type'] == 'PLAINTEXT':
            return PlainTextView(**msg['view'])
        elif msg['view_type'] == 'PLACE':
            return PlaceView(**msg['view'])
        elif msg['view_type'] == 'MEDIA':
            return MediaView(**msg['view'])

    members = await redis.hkeys(f'channels#{channel}#members')

    message_response = MessageResponse(
        message_id=str(uuid.uuid4()),
        view_type=message['view_type'],
        view=await typed(message),
        created_at=message['date'],
        created_by=User(**await redis.hgetall(f"users#{message['service']}#{message['from']}"))
    )

    await func_asyncio(table.put_item, Item={'channel_id': channel, **message_response.dict()})
    await redis.publish(channel, f"{message['service']}#{message['from']}: {message['view']['message']}")
    await push(channel, members)


async def push(channel: str, members: list):
    pass


@app.post("/channels/{channel}/{service}/{user_id}", tags=["Websocket"])
async def fake_websocket(channel: str, service: Service, user_id: str):
    """Try changing the protocol to websocket"""
    pass


@app.post("/channels/_message", tags=["Websocket"])
async def fake_websocket_message(message: Message):
    """Format the message you send after connecting to the websocket"""
    pass
