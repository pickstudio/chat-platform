import asyncio
import time
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
from .settings import Settings

app = FastAPI()
settings = Settings()
logger = logging.getLogger('uvicorn')
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


@app.get("/chat", tags=["chat"])
async def get():
    return HTMLResponse(html)


@app.get("/chat/list/{user_id}", response_model=list, tags=["chat"])
async def room_list(user_id: Union[str, int]) -> list:
    """채팅방 리스트 조회"""
    return await redis.smembers(f"user:{user_id}")


@app.post("/chat/create", tags=["chat"])
async def room_create(requests: RoomCreateRequest):
    """채팅방 생성 -> 유저별 채팅방 리스트 추가 -> 채팅방 id 리턴"""
    pass


@app.get("/chat/message/{room_id}", tags=["chat"])
async def messages(room_id: Union[str, int]):
    """채팅방 메세지 조회"""
    pass


@app.websocket("/chat/{user_id}/{room_id}")
async def websocket_endpoint(params: ChatRequest = Depends()):
    await params.ws.accept()
    await connection(params)


async def connection(params: ChatRequest):
    await online(params.user_id)
    user_ids: list = params.room_id.split(":")

    is_online_exists: bool = await online_exists(params.room_id)
    is_online_exists = True

    await chat(params)


async def online(user_id: Union[str, int]) -> None:
    await redis.sadd("online_users", user_id)


async def online_exists(user_id: Union[str, int]) -> bool:
    return await redis.sismember("online_users", user_id)


async def chat(params: ChatRequest):
    async def client_handler(ws: WebSocket):
        """client 메세지 처리"""
        try:
            while True:
                message = await ws.receive_text()
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

    pubsub: PubSub = redis.pubsub()
    await pubsub.subscribe(params.room_id)

    pubsub_task = pubsub_handler(params.ws)
    client_task = client_handler(params.ws)

    done, pending = await asyncio.wait(
        [pubsub_task, client_task], return_when=asyncio.FIRST_EXCEPTION,
    )

    logger.info(f"Done task: {done}")
    for task in pending:
        logger.info(f"Canceling task: {task}")
        task.cancel()


async def broadcast(room_id: Union[str, int], message: str):
    await redis.publish(room_id, f'{message}')
    user_ids: list = room_id.split(":")

    """채팅방 온라인 체크"""
    """False : push notification"""

    await redis.zadd(f'room:{room_id}', {json.dumps({"message": message}): int(time.time())})
