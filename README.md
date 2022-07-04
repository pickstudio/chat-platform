# 채팅 서버
공통적으로 이용할 수 있는 채팅 서비스입니다.

하기 API를 통해 사용할 수 있습니다.

## REST API Docs
기본적인 REST API는 Open API를 통해서 제공되고 있습니다.

서버 실행 후 아래의 경로를 통해 확인이 가능합니다.
```
path : /docs
       /redoc
```

## WebSocket API Docs
웹소켓은 Open API를 통해 제공할 수 없기 때문에 README.md 파일에 명세하고 있습니다.
```
* 웹소켓 연결
protocol : ws
path : /chat/{user_id}/{room_id}
type :
  - user_id : str
  - room_id : str
example :
  - user_id : "5"
  - room_id : "5:10"
  - ws://localhost/chat/5/5:10

* 메세지
format : json
type :
  - timestamp : bigint
  - message : str
  - from(user_id) : str
example : {
  "date": 1653143651892,
  "message": "hello world",
  "from": "dd9c549dbadddd20c12f8bce48bcec581341e0dd27f764ae18af645c0dd75803"
}
```
### Detail
* protocol : Scheme ***(e.g. http, https, ws)***
* path : The endpoint ***(route)***
* room_id = `user_id:user_id`

  ( **:** 구분자를 통해서 유저 아이디끼리 연결된 형태 )

  (순서에 대한 구분은 없기 때문에 `/room/list/{user_id}` 를 통해 받은 room_id 사용)


## Getting Started

### 환경변수 입력

`.env.sample` 파일을 `.env` 파일로 복사 후 환경변수 입력

또는

`Github Secrets`를 통해 `.env` 파일 생성

### 실행
```
docker-compose up -d
```
