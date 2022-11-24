from enum import Enum
from typing import Union

from pydantic import BaseModel, Field


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
    source: dict
    meta: dict


class User(BaseModel):
    service: Service
    user_id: str
    nickname: str
    source: Union[str, dict]
    meta: Union[str, dict]


class TokenRequest(BaseModel):
    push_token: str


class TokenResponse(BaseModel):
    token: str
    token_type: TokenType
    user: User


class TokenRemoveResponse(BaseModel):
    tokens: list[str]
    token_type: TokenType
    user: User


class Coordinate(BaseModel):
    latitude: str
    longitude: str


class PlaceInfo(BaseModel):
    name: str
    parent_name: str
    category: str
    star_point: str


class PlainTextView(BaseModel):
    message: str


class PlaceView(BaseModel):
    coordinate: Coordinate
    place_info: PlaceInfo
    timestamp: int


class MediaView(BaseModel):
    url: str


class Message(BaseModel):
    service: Service
    user_id: str
    channel_id: str
    view_type: ViewType
    view: Union[PlainTextView, PlaceView, MediaView]
    date: int = Field(example=1665065862437)


class MessageRequest(BaseModel):
    service: Service
    user_id: str


class MessageResponse(BaseModel):
    message_id: str
    view_type: ViewType
    view: Union[PlainTextView, PlaceView, MediaView, str]
    created_at: int
    created_by: Union[User, str]


class MessageListResponse(BaseModel):
    last_read_time: int
    messages: list[MessageResponse]


class Member(BaseModel):
    service: Service
    user_id: str


class MemberWithState(BaseModel):
    service: Service
    user_id: str
    nickname: str
    state: str
    source: Union[str, dict]
    meta: Union[str, dict]


class Channel(BaseModel):
    channel: str
    type: ChannelType
    created_at: int


class ChannelListResponse(BaseModel):
    channel: str
    type: ChannelType
    member_count: int
    joined_member_count: int
    members: Union[list[MemberWithState], str]
    unread_message_count: int
    last_message: Union[MessageResponse, str, dict]
    created_at: int


class ChannelList(BaseModel):
    channels: list[ChannelListResponse]


class ChannelRequest(BaseModel):
    members: list[Member]


class ChannelResponse(BaseModel):
    channel: str
    type: ChannelType
