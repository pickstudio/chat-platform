from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from starlette.websockets import WebSocket


class Service(str, Enum):
    PICKME = 'PICKME'
    DIJKSTRA = 'DIJKSTRA'


class TokenType(str, Enum):
    FCM = "FCM"
    APNS = "APNS"


class ChannelType(str, Enum):
    ONE_ON_ONE = "ONE_ON_ONE"
    GROUP = "GROUP"


class ViewType(str, Enum):
    PLAINTEXT = "PLAINTEXT"
    PLACE = "PLACE"
    MEDIA = "MEDIA"


class User(BaseModel):
    nickname: str
    source: Optional[dict]
    meta: Optional[dict]


class UserObject(BaseModel):
    service: Service
    user_id: str
    nickname: str


class Token(BaseModel):
    user_agent: str
    token_type: TokenType
    push_token: str
    source: Optional[dict]
    meta: Optional[dict]


class TokenResponse(BaseModel):
    tokens: list[Token]
    user: UserObject


class TokenObject(BaseModel):
    tokens: list[Token]
    user: UserObject


class Message(BaseModel):
    view_type: str
    view: dict
    user: UserObject
    created_at: int
    source: Optional[dict] = Field(..., alias="_source")
    meta: Optional[dict] = Field(..., alias="_meta")


class MessageResponse(BaseModel):
    message_id: int
    view_type: str
    view: dict
    created_at: int
    created_by: UserObject


class Member(BaseModel):
    service: Service
    user_id: str


class Channel(BaseModel):
    channel: str
    type: ChannelType
    member_count: int
    members: list[UserObject]
    last_read_at: list[dict]
    unread_message_count: int
    last_message: MessageResponse
    created_at: int
    created_by: UserObject


class ChannelRequest(BaseModel):
    members: list[Member]
    type: ChannelType


class ChannelResponse(BaseModel):
    channel: str


class RoomCreateRequest(BaseModel):
    user_id: str
    target_id: str


class ResponseMessage(BaseModel):
    message: str


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
