import asyncio
import time
import uuid
from typing import Any

from aioredis.client import PubSub
from fastapi import FastAPI, Depends
from starlette.websockets import WebSocketDisconnect

from config.db import *
from config.models import *
from config.settings import Settings
from config.logging import logger, log_request

app = FastAPI(
    title="Chat Message",
    version="0.1.0",
    description="Pickstudio chat message server",
    contact={
        "name": "Heyho",
        "email": "nerolizm@gmail.com"
    }
)
settings = Settings()
redis: Union[Redis, None] = None
table: Any = None

THOUSAND_TIMES: int = 1000


@app.on_event('startup')
async def startup():
    global redis, table
    redis = await get_redis_pool()
    table = await get_table(await get_dynamo())


@app.on_event('shutdown')
async def shutdown():
    await redis.close()


@app.get("/chat", tags=["chat"], include_in_schema=False)
async def get():
    from starlette.responses import HTMLResponse
    from server.message.html import html
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
            await marked_as_read(request.member.service, request.member.user_id, request.channel)

    async def pubsub_handler(ws: WebSocket):
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    await ws.send_text(message.get('data'))
        except Exception as exc:
            logger.info(f'{pubsub_handler.__name__} : {exc}')

    await marked_as_read(request.member.service, request.member.user_id, request.channel)

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


async def marked_as_read(service: Service, user_id: str, channel_id: str, read_time: int = None) -> None:
    await redis.hset(
        name=f'channels#{channel_id}#status',
        key=f'{service}#{user_id}#read',
        value=read_time or int(time.time() * THOUSAND_TIMES)
    )


@log_request
async def broadcast(channel: str, message: dict):
    async def push(members: list):
        pass

    async def typed(msg):
        if msg['view_type'] == 'PLAINTEXT':
            return PlainTextView(**msg['view'])
        elif msg['view_type'] == 'PLACE':
            return PlaceView(**msg['view'])
        elif msg['view_type'] == 'MEDIA':
            return MediaView(**msg['view'])

    message_response = MessageResponse(
        message_id=str(uuid.uuid4()),
        view_type=ViewType(message['view_type']),
        view=await typed(message),
        created_at=message['date'],
        created_by=User(**await redis.hgetall(f"users#{message['service']}#{message['from']}"))
    )

    await func_asyncio(table.put_item, Item={'channel_id': channel, **message_response.dict()})
    await redis.publish(channel, message_response.json(ensure_ascii=False))
    await push(await redis.hkeys(f'channels#{channel}#members'))


@app.post("/channels/{channel}/{service}/{user_id}", tags=["Websocket"])
async def fake_websocket(channel: str, service: Service, user_id: str):
    """Try changing the protocol to websocket"""
    pass


@app.post("/channels/_message", response_model=MessageResponse, tags=["Websocket"])
async def fake_websocket_message(message: Message):
    """Format the message you send after connecting to the websocket"""
    pass
