from typing import Union

from pydantic import BaseModel
from starlette.websockets import WebSocket


class HealthCheckResponse(BaseModel):
    message: str


class RoomCreateRequest(BaseModel):
    user_id: Union[str, int]
    target_id: Union[str, int]


class ChatRequest:
    def __init__(
        self,
        ws: WebSocket,
        user_id: Union[str, int] = None,
        room_id: Union[str, int] = None,
        q: Union[str, None] = None,
    ):
        self.ws = ws
        self.user_id = user_id
        self.room_id = room_id
        self.q = q
