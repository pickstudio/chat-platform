from pydantic import BaseModel
from starlette.websockets import WebSocket


class HealthCheckResponse(BaseModel):
    message: str


class RoomCreateRequest(BaseModel):
    user_id: str
    target_id: str


class ChatRequest:
    def __init__(
        self,
        ws: WebSocket,
        user_id: str,
        room_id: str
    ):
        self.ws = ws
        self.user_id = user_id
        self.room_id = room_id
