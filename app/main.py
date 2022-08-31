import json
import logging
from typing import Union, Any

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.logger import logger

from .models import *
from .db import *
from .settings import Settings

app = FastAPI()
settings = Settings()
redis: Union[Redis, None] = None
table: Any = None

gunicorn_logger = logging.getLogger('gunicorn.error')
logger.handlers = gunicorn_logger.handlers
logger.setLevel(logging.DEBUG)

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


@app.get("/", status_code=200)
async def health_check():
    return


@app.put("/users/{service}/{user_id}", response_model=UserObject, tags=["user"])
async def upsert_user(service: Service, user_id: str, request: User):
    """유저 정보 등록/수정"""
    logger.info(request.dict())

    await redis.hset(name=f'users#{service}', key=user_id, value=request.json(ensure_ascii=False))

    return UserObject(service=service, user_id=user_id, **request.dict())


@app.delete("/users/{service}/{user_id}", tags=["user"])
async def delete_user(service: Service, user_id: str):
    """유저 정보 삭제"""
    if await redis.hdel(f'users#{service}', user_id):
        return JSONResponse({'message': f'User deleted successfully'}, status.HTTP_200_OK)


@app.post("/users/{service}/{user_id}/tokens",
          response_model=TokenResponse,
          responses={status.HTTP_400_BAD_REQUEST: {"model": ResponseMessage}},
          tags=["token"])
async def register_token(service: Service, user_id: str, request: Token):
    """푸시 토큰 등록"""
    logger.info(request.dict())

    user = await redis.hget(f'users#{service}', user_id)

    if not user:
        return JSONResponse(content={"message": "User not exist"}, status_code=status.HTTP_400_BAD_REQUEST)

    key = f'users#{service}#{user_id}'

    await redis.hset(name=key, key=request.token_type, value=request.json(ensure_ascii=False))

    return TokenResponse(
        tokens=list(map(lambda item: json.loads(item[1]), dict(await redis.hgetall(key)).items())),
        user=UserObject(service=service, user_id=user_id, **json.loads(user))
    )


@app.delete("/users/{service}/{user_id}/tokens", tags=["token"])
async def delete_all_tokens(service: Service, user_id: str):
    """푸시 토큰 전체 등록 해제"""
    await redis.delete(f'users#{service}#{user_id}')


@app.delete("/users/{service}/{user_id}/tokens/{token_type}/{token}", response_model=TokenObject, tags=["token"])
async def delete_token(service: Service, user_id: str, token_type: TokenType, token: str):
    """푸시 토큰 등록 해제"""
    pass


@app.get("/channels/{service}/{user_id}", response_model=list[Channel], tags=["channel"])
async def list_channels(service: Service, user_id: str):
    """채팅 채널 리스트"""
    pass


@app.post("/channels", response_model=ChannelResponse, tags=["channel"])
async def create_channel(request: ChannelRequest):
    """채팅 채널 생성"""
    pass


@app.put("/channels/{channel}/join", tags=["channel"])
async def join_channel(channel: str, request: Member):
    """채팅 채널 입장"""
    pass


@app.put("/channels/{channel}/leave", tags=["channel"])
async def join_channel(channel: str, request: Member):
    """채팅 채널 퇴장"""
    pass


@app.get("/channels/{channel}/messages", response_model=list[MessageResponse], tags=["message"])
async def list_messages(channel: str):
    """채팅 내역 리스트"""
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
