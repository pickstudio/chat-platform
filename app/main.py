import asyncio
import json
import logging
import time
import uuid
from json import JSONDecodeError
from typing import Any

from aioredis.client import PubSub
from fastapi import FastAPI, status, Depends
from fastapi.responses import JSONResponse
from fastapi.logger import logger
from pydantic.json import pydantic_encoder
from starlette.websockets import WebSocketDisconnect

from .models import *
from .db import *
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
dynamo_client: Any = None

gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)

THOUSAND_TIMES: int = 1000
MAX_MESSAGE_COUNT: int = 300


@app.on_event('startup')
async def startup():
    global redis, table, dynamo_client
    redis = await get_redis_pool()
    dynamo = await get_dynamo()
    dynamo_client = await get_dynamo_client()
    table = await get_table(dynamo)


@app.on_event('shutdown')
async def shutdown():
    await redis.close()


@app.get("/", status_code=200, include_in_schema=False)
async def health_check():
    return


@app.put("/users/{service}/{user_id}", response_model=User, tags=["User"])
async def upsert_user(service: Service, user_id: str, request: UserRequest):
    """Register/modify user"""
    logger.info(request.dict())

    user = User(service=service, user_id=user_id, **request.dict())

    await redis.hset(name=f'users#{service}', key=user_id, value=user.json(ensure_ascii=False))

    return user


@app.delete("/users/{service}/{user_id}", tags=["User"])
async def delete_user(service: Service, user_id: str):
    """Delete user"""
    if await redis.hdel(f'users#{service}', user_id):
        return JSONResponse({'message': f'User deleted successfully'}, status.HTTP_200_OK)


@app.put("/users/{service}/{user_id}/tokens", response_model=TokenResponse, tags=["Token"])
async def register_token(service: Service, user_id: str, request: Token):
    """Register/modify push token (can maintain one per token type)"""
    logger.info(request.dict())

    user = await redis.hget(f'users#{service}', user_id)
    key = f'users#{service}#{user_id}#tokens'

    await redis.hset(name=key, key=request.token_type, value=request.json(ensure_ascii=False))

    return TokenResponse(
        tokens=list(map(lambda value: json.loads(value), dict(await redis.hgetall(key)).values())),
        user=User(**json.loads(user))
    )


@app.delete("/users/{service}/{user_id}/tokens", tags=["Token"])
async def delete_all_tokens(service: Service, user_id: str):
    """Unregister whole push token"""
    await redis.delete(f'users#{service}#{user_id}#tokens')


@app.delete("/users/{service}/{user_id}/tokens/{token_type}/{token}", response_model=TokenObject, tags=["Token"])
async def delete_token(service: Service, user_id: str, token_type: TokenType):
    """Unregister specific push token"""
    await redis.hdel(f'users#{service}#{user_id}#tokens', token_type)


@app.post("/channels", response_model=ChannelResponse, tags=["Channel"])
async def create_channel(request: ChannelRequest):
    """Create channel"""
    logger.info(request.dict())

    timestamp = int(time.time() * THOUSAND_TIMES)
    channel_id = str(uuid.uuid4())
    users = list()

    for member in request.members:
        users.append(json.loads(await redis.hget(f'users#{member.service}', member.user_id)))
        await redis.sadd(f'users#{member.service}#{member.user_id}#channels', channel_id)
        await redis.hset(f'channels#{channel_id}#status', f'{member.service}#{member.user_id}#read', timestamp)

    channel = Channel(
        channel=channel_id,
        type=request.type,
        member_count=len(request.members),
        members=json.dumps(users, default=pydantic_encoder, ensure_ascii=False),
        last_message='{}',
        created_at=timestamp
    )

    await redis.hset(f'channels#{channel_id}', mapping=channel.dict())

    return ChannelResponse(channel=channel_id)


@app.get("/channels/{service}/{user_id}", response_model=ChannelList, tags=["Channel"])
async def list_channels(service: Service, user_id: str):
    """List channels"""
    channels = list()
    channel_list = await redis.smembers(f'users#{service}#{user_id}#channels')

    def decode(item):
        try:
            return item[0], json.loads(item[1])
        except JSONDecodeError:
            return item[0], item[1]

    async def unread_count(cid, svc, uid) -> int:
        last_read = await redis.hget(f'channels#{cid}#status', f'{svc}#{uid}#read')
        query = {
            "Statement": "select * from pickpublic_chat where channel_id=? and created_at>?",
            "Parameters": [
                {"S": cid}, {"N": last_read}
            ]
        }
        result = await func_asyncio(dynamo_client.execute_statement, **query)
        return len(result['Items'])

    for channel_id in channel_list:
        channel = dict(await redis.hgetall(f'channels#{channel_id}'))
        channel = dict(map(decode, channel.items()))
        unread_message_count: int = await unread_count(channel_id, service, user_id)
        channels.append(ChannelListResponse(unread_message_count=unread_message_count, **channel))

    return ChannelList(channels=channels)


@app.put("/channels/{channel}/join", tags=["Channel"], deprecated=True)
async def join_channel(channel: str, request: Member):
    """Join the channel"""
    pass


@app.put("/channels/{channel}/leave", tags=["Channel"], deprecated=True)
async def leave_channel(channel: str, request: Member):
    """Leave the channel"""
    pass


@app.get("/channels/{channel}/messages", response_model=list[MessageResponse], tags=["Message"])
async def list_messages(channel: str):
    """List messages"""
    pass


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
    await redis.hdel(f'channels#{request.channel}#status', f'{request.member.service}#{request.member.user_id}#read')


async def leave(request: ChatRequest):
    await redis.hset(
        f'channels#{request.channel}#status',
        f'{request.member.service}#{request.member.user_id}#read',
        int(time.time() * THOUSAND_TIMES)
    )


async def broadcast(channel: str, message: dict):
    logger.info(message)
    members = json.loads(await redis.hget(f'channels#{channel}', 'members'))

    msg = MessageResponse(
        message_id=str(uuid.uuid4()),
        view_type=message['view_type'],
        view=json.dumps(message['view'], default=pydantic_encoder, ensure_ascii=False),
        created_at=message['date'],
        created_by=await redis.hget(f"users#{message['service']}", message['from'])
    )

    msg_json = msg
    msg_json.view = json.loads(msg_json.view)
    msg_json.created_by = json.loads(msg_json.created_by)

    await func_asyncio(table.put_item, Item={'channel_id': channel, **msg.dict()})
    await redis.hset(f'channels#{channel}', 'last_message', msg_json.json(ensure_ascii=False))
    await redis.publish(channel, f"{message['service']}#{message['from']}: {message['view']['message']}")
    await push(channel, members)


async def push(channel: str, members: list):
    for member in members:
        last_read = await redis.hget(f'channels#{channel}#status', f"{member['service']}#{member['user_id']}#read")

        if last_read:
            """do push"""
            pass


@app.get("/channels/{channel}/{service}/{user_id}", tags=["Websocket"])
async def fake_websocket(channel: str, service: Service, user_id: str):
    """Try changing the protocol to websocket"""
    pass


@app.get("/channels/_message", tags=["Websocket"])
async def fake_websocket_message(message: Message):
    """Format the message you send after connecting to the websocket"""
    pass
