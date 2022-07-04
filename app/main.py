import asyncio
import json
import logging

import aioredis
from aioredis import Redis
from aioredis.client import PubSub
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.websockets import WebSocketDisconnect

from .html import html
from .models import *
from .db import *
from .settings import Settings

app = FastAPI()
settings = Settings()
logger = logging.getLogger('uvicorn')
settings = Settings()
redis: Union[Redis, None] = None


@app.on_event('startup')
async def startup() -> None:
    global redis
    redis = await get_redis_pool()


@app.on_event('shutdown')
async def shutdown() -> None:
    await redis.close()


async def get_redis_pool() -> Redis:
    return await aioredis.from_url(
        f'redis://{settings.redis.redis_host}',
        password=f'{settings.redis.redis_password}',
        encoding='utf-8',
        decode_responses=True
    )


@app.get("/", response_model=HealthCheckResponse)
async def health_check() -> JSONResponse:
    """health check"""
    return JSONResponse(content={"message": "health"})


@app.get("/room/list/{user_id}", response_model=list, tags=["room"])
async def get_room_list(user_id: str) -> list:
    """채팅방 리스트 조회"""
    return await redis.smembers(f"user:{user_id}:rooms")


@app.post("/room/create", response_model=str, tags=["room"])
async def create_room(request: RoomCreateRequest) -> str:
    """채팅방 생성 -> 유저별 채팅방 리스트 추가 -> 채팅방 리턴"""
    room_id = ":".join(list(request.dict().values()))

    for key, user_id in request:
        await redis.sadd(f"user:{user_id}:rooms", room_id)

    return room_id


@app.get("/room/message/{room_id}", response_model=list, tags=["room"])
async def messages(room_id: str) -> list:
    """채팅방 메세지 조회"""
    return await redis.zrange(f"room:{room_id}", 0, -1)


@app.post("/chat/online/{user_id}", tags=["chat"])
async def online(user_id: Union[str, int]) -> None:
    """온라인 상태로 변경"""
    await redis.sadd("online_users", user_id)


@app.delete("/chat/offline/{user_id}", tags=["chat"])
async def offline(user_id: Union[str, int]) -> None:
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
            await redis.publish(params.room_id, f'Client {params.user_id} left the chat')

    async def pubsub_handler(ws: WebSocket):
        """Pub/Sub 메세지 처리"""
        await redis.publish(params.room_id, f'Client {params.user_id} joined the {params.room_id}')
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

    await leave(params.user_id, params.room_id)

    for task in pending:
        logger.info(f"Canceling task: {task}")
        task.cancel()


async def enter(user_id: Union[str, int], room_id: str) -> None:
    """채팅방 접속"""
    await redis.sadd(f"room:{room_id}:online", user_id)


async def leave(user_id: Union[str, int], room_id: str) -> None:
    """채팅방 이탈"""
    await redis.srem(f"room:{room_id}:online", user_id)


async def broadcast(room_id: str, message: dict):
    """publish + push notification"""
    all_user_ids: list = room_id.split(":")
    entered_user_ids: list = await redis.smembers(f"room:{room_id}:online")
    offline_user_ids: list = list(set(all_user_ids) ^ set(entered_user_ids))

    message_json: str = json.dumps(message)

    """Publish"""
    await redis.publish(room_id, message['message'])

    """Push Notification"""

    await redis.zadd(f'room:{room_id}', {message_json: int(message['date'])})

    """history"""
    await func_asyncio(put_item(dynamodb, settings.dynamodb.table_name), Item={
        'user_id': 'c',
        'status': 0
    })


async def push_noti(user_ids: list):
    pass
