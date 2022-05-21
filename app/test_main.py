from .main import app, redis
from fastapi.testclient import TestClient

client = TestClient(app)


def test_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "health"}


def test_room_list():
    response = client.get("/room/list/1")
    assert response.status_code == 200


def test_room_create():
    faker_data = {
        "user_id": 1,
        "target_id": 2
    }
    response = client.post(
        "/room/create",
        json=faker_data
    )
    assert response.status_code == 200
    assert response == "1:2"

    for key, user_id in faker_data:
        redis.srem(f"user:{user_id}:rooms", response)


def test_room_message():
    response = client.get("/room/message/1:2")
    assert response.status_code == 200


def test_online():
    response = client.get("/chat/online/1")
    assert response.status_code == 200


def test_offline():
    response = client.get("/chat/online/1")
    assert response.status_code == 200


def test_websocket():
    with client.websocket_connect("/ws/1/1:2") as ws:
        data = ws.receive_json()
        assert data == {"msg": "Hello WebSocket"}
