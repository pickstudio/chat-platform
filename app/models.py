from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel
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


class UserRequest(BaseModel):
    nickname: str
    source: Optional[dict]
    meta: Optional[dict]


class User(BaseModel):
    service: Service
    user_id: str
    nickname: str
    source: Optional[dict]
    meta: Optional[dict]


class Token(BaseModel):
    user_agent: str
    token_type: TokenType
    push_token: str
    source: Optional[dict]
    meta: Optional[dict]


class TokenResponse(BaseModel):
    tokens: list[Token]
    user: User


class TokenObject(BaseModel):
    tokens: list[Token]
    user: User


class Coordinate(BaseModel):
    latitude: float
    longitude: float


class PlaceInfo(BaseModel):
    name: str
    parent_name: str
    category: str
    star_point: float


class PlainTextView(BaseModel):
    message_id: int
    message: str
    source: Optional[dict]
    meta: Optional[dict]


class PlaceView(BaseModel):
    message_id: int
    coordinate: Coordinate
    place_info: PlaceInfo
    timestamp: int
    source: Optional[dict]
    meta: Optional[dict]


class MediaView(BaseModel):
    message_id: int
    url: str
    source: Optional[dict]
    meta: Optional[dict]


class Message(BaseModel):
    view_type: ViewType
    view: Union[PlainTextView, PlaceView, MediaView]
    source: Optional[dict]
    meta: Optional[dict]


class MessageResponse(BaseModel):
    message_id: int
    view_type: ViewType
    view: Union[PlainTextView, PlaceView, MediaView]
    created_at: int
    created_by: User


class Member(BaseModel):
    service: Service
    user_id: str


class Channel(BaseModel):
    channel: str
    type: ChannelType
    member_count: int
    members: Union[list[User], str]
    unread_message_count: int
    last_message: Union[MessageResponse, str, dict]
    created_at: int


class ChannelList(BaseModel):
    channels: list[Channel]


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
        channel: str,
        service: Service,
        user_id: str
    ):
        self.ws = ws
        self.channel = channel
        self.service = service
        self.user_id = user_id
