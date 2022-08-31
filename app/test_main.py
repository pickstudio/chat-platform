import pytest

from .main import app
from fastapi.testclient import TestClient

service: str = "PICKME"
user_id: str = "test"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_main(client):
    response = client.get("/")
    assert response.status_code == 200


def test_upsert_user(client):
    response = client.put(f"/users/{service}/{user_id}", json={
        "nickname": "테스트유저",
        "source": {
            "tmp1": "t1",
            "tmp2": "t2"
        },
        "meta": {
            "meta_tmp1": "meta_t1",
            "meta_tmp2": "meta_t2"
        }
    })
    assert response.status_code == 200


def test_register_token(client):
    response = client.post(f"/users/{service}/{user_id}/tokens", json={
      "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1",
      "token_type": "APNS",
      "push_token": "740f4707 bebcf74f 9b7c25d4 8e335894 5f6aa01d a5ddb387 462c7eaf 61bb78ad",
      "source": {},
      "meta": {}
    })
    assert response.status_code == 200


def test_delete_user(client):
    response = client.delete(f"/users/{service}/{user_id}")
    assert response.status_code == 200


def test_delete_all_tokens(client):
    response = client.delete(f"/users/{service}/{user_id}/tokens")
    assert response.status_code == 200
