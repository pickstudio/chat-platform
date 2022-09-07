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

gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)

THOUSAND_TIMES: int = 1000
MAX_MESSAGE_COUNT: int = 300


@app.on_event('startup')
async def startup():
    global redis, table
    redis = await get_redis_pool()
    dynamo = await get_dynamo()
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
async def delete_token(service: Service, user_id: str, token_type: TokenType, token: str):
    """Unregister specific push token"""
    pass


@app.get("/channels/{service}/{user_id}", response_model=ChannelList, tags=["Channel"])
async def list_channels(service: Service, user_id: str):
    """List channels"""
    channel_list = await redis.lrange(f'users#{service}#{user_id}#channels', 0, -1)
    channels = list()

    def decode(item):
        try:
            return item[0], json.loads(item[1])
        except JSONDecodeError:
            return item[0], item[1]

    for channel_id in channel_list:
        channel = dict(await redis.hgetall(f'channels#{channel_id}'))
        channel = dict(map(decode, channel.items()))
        channels.append(Channel(**channel))

    return ChannelList(channels=channels)


@app.post("/channels", response_model=ChannelResponse, tags=["Channel"])
async def create_channel(request: ChannelRequest):
    """Create channel"""
    logger.info(request.dict())

    channel_id = str(uuid.uuid4())
    users = list()

    for member in request.members:
        users.append(json.loads(await redis.hget(f'users#{member.service}', member.user_id)))
        await redis.lpush(f'users#{member.service}#{member.user_id}#channels', channel_id)

    channel = Channel(
        channel=channel_id,
        type=request.type,
        member_count=len(request.members),
        members=json.dumps(users, default=pydantic_encoder, ensure_ascii=False),
        unread_message_count=0,
        last_message='{}',
        created_at=int(time.time() * THOUSAND_TIMES)
    )

    await redis.hset(f'channels#{channel_id}', mapping=channel.dict())

    return ChannelResponse(channel=channel_id)


@app.put("/channels/{channel}/join", tags=["Channel"], deprecated=True)
async def join_channel(channel: str, request: Member):
    """Join the channel"""
    pass


@app.put("/channels/{channel}/leave", tags=["Channel"])
async def leave_channel(channel: str, request: Member):
    """Leave the channel"""
    pass


@app.get("/channels/{channel}/messages", response_model=list[MessageResponse], tags=["Message"])
async def list_messages(channel: str):
    """List messages"""
    pass


@app.get("/channels/{channel}/{service}/{user_id}", tags=["Websocket"])
async def fake_websocket(channel: str, service: Service, user_id: str):
    """Try changing the protocol to websocket"""
    pass


@app.get("/channels/_message", tags=["Websocket"])
async def fake_websocket_message(message: Message):
    """Format the message you send after connecting to the websocket"""
    pass


@app.get("/chat", tags=["chat"], include_in_schema=False)
async def get():
    from starlette.responses import HTMLResponse
    from app.html import html
    return HTMLResponse(html)


@app.websocket("/channels/{channel}/{service}/{user_id}")
async def websocket_endpoint(params: ChatRequest = Depends()):
    await params.ws.accept()
    await connection(params)


async def connection(params: ChatRequest):
    async def client_handler(ws: WebSocket):
        """client 메세지 처리"""
        try:
            while True:
                message = await ws.receive_json()
                if message:
                    await broadcast(params.channel, message=message)
        except WebSocketDisconnect:
            # await leave(params.user_id, params.channel)
            pass

    async def pubsub_handler(ws: WebSocket):
        """Pub/Sub 메세지 처리"""
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await ws.send_text(message.get('data'))
        except Exception as exc:
            logger.info(f'{pubsub_handler.__name__} : {exc}')

    pubsub: PubSub = redis.pubsub()
    await pubsub.subscribe(params.channel)

    pubsub_task = pubsub_handler(params.ws)
    client_task = client_handler(params.ws)

    done, pending = await asyncio.wait(
        [pubsub_task, client_task], return_when=asyncio.FIRST_EXCEPTION,
    )

    for task in pending:
        logger.info(f"Canceling task: {task}")
        task.cancel()


async def enter(user_id: str, room_id: str) -> None:
    await redis.sadd(f"room:{room_id}:online", user_id)


async def leave(user_id: str, room_id: str) -> None:
    await redis.srem(f"room:{room_id}:online", user_id)


async def broadcast(service: str, message: dict):
    logger.info(message)
    all_user_ids: list = service.split(":")
    # online_user_ids: list = await redis.smembers(f"room:{service}:online")
    # offline_user_ids: list = list(set(all_user_ids) ^ set(online_user_ids))

    message_json: str = json.dumps(message)

    """Publish"""
    await redis.publish(service, f"{message['from']}: {message['message']}")

    """Push Notification"""
    # await push(offline_user_ids)

    """redis """
    # await redis.zadd(f'room:{room_id}', {message_json: int(message['date'])})

    """history"""
    # await func_asyncio(table.put_item, Item={
    #     'user_id': message['from'],
    #     'status': 0,
    #     'message': message_json
    # })


async def push(user_ids: list):
    pass





'''
@app.get("/room/list/{user_id}", response_model=list, tags=["room"])
async def get_room_list(user_id: str) -> list:
    """채팅방 리스트 조회"""
    return await redis.smembers(f"user:{user_id}:rooms")


@app.post("/room/create", response_model=str, tags=["room"])
async def create_room(request: RoomCreateRequest) -> str:
    """채팅방 생성 -> 유저별 채팅방 리스트 추가 -> 채팅방 리턴"""
    room_id = ":".join(list(request.dict().values()))

    if await redis.exists(f"room:{room_id}"):
        return room_id

    for _, user_id in request:
        await redis.sadd(f"user:{user_id}:rooms", room_id)

    return room_id


@app.get("/room/message/{room_id}", response_model=list, tags=["room"])
async def messages(room_id: str) -> list:
    """채팅방 메세지 조회"""
    return await redis.zrangebyscore(f"room:{room_id}", min="-inf", max="+inf", start=0, num=MAX_MESSAGE_COUNT)


@app.post("/chat/online/{user_id}", tags=["chat"])
async def online(user_id: str) -> None:
    """온라인 상태로 변경"""
    await redis.sadd("online_users", user_id)


@app.delete("/chat/offline/{user_id}", tags=["chat"])
async def offline(user_id: str) -> None:
    """오프라인 상태로 변경"""
    await redis.srem("online_users", user_id)


@app.get("/chat", tags=["chat"])
async def get():
    return HTMLResponse(html)


@app.websocket("/chat/{user_id}/{room_id}")
async def websocket_endpoint(params: ChatRequest = Depends()):
    """웹소켓 엔드 포인트"""
    await params.ws.accept()
    await connection(params)


async def connection(params: ChatRequest):
    async def client_handler(ws: WebSocket):
        """client 메세지 처리"""
        try:
            while True:
                message = await ws.receive_json()
                if message:
                    await broadcast(params.room_id, message=message)
        except WebSocketDisconnect:
            await leave(params.user_id, params.room_id)

    async def pubsub_handler(ws: WebSocket):
        """Pub/Sub 메세지 처리"""
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await ws.send_text(message.get('data'))
        except Exception as exc:
            logger.info(f'{pubsub_handler.__name__} : {exc}')

    await enter(params.user_id, params.room_id)

    pubsub: PubSub = redis.pubsub()
    await pubsub.subscribe(params.room_id)

    pubsub_task = pubsub_handler(params.ws)
    client_task = client_handler(params.ws)

    done, pending = await asyncio.wait(
        [pubsub_task, client_task], return_when=asyncio.FIRST_EXCEPTION,
    )

    for task in pending:
        logger.info(f"Canceling task: {task}")
        task.cancel()


async def enter(user_id: str, room_id: str) -> None:
    """채팅방 접속"""
    await redis.sadd(f"room:{room_id}:online", user_id)


async def leave(user_id: str, room_id: str) -> None:
    """채팅방 이탈"""
    await redis.srem(f"room:{room_id}:online", user_id)


async def broadcast(room_id: str, message: dict):
    """publish + push notification"""
    logger.info(message)
    all_user_ids: list = room_id.split(":")
    online_user_ids: list = await redis.smembers(f"room:{room_id}:online")
    offline_user_ids: list = list(set(all_user_ids) ^ set(online_user_ids))

    message_json: str = json.dumps(message)

    """Publish"""
    await redis.publish(room_id, message['message'])

    """Push Notification"""
    await push(offline_user_ids)

    """redis """
    await redis.zadd(f'room:{room_id}', {message_json: int(message['date'])})

    """history"""
    await func_asyncio(table.put_item, Item={
        'user_id': message['from'],
        'status': 0,
        'message': message_json
    })


async def push(user_ids: list):
    pass
'''
