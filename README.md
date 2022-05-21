# 채팅 서버
공통적으로 이용할 수 있는 채팅 서비스입니다.
하기 API를 통해 사용할 수 있습니다.

## API
```
protocol : ws
path : /chat/{client_id}/{room_id}
description : {
    'client_id': ['required', 'integer'],
    'target_id': ['required', 'integer']
}
```
### 설명
* protocol : scheme ***(e.g. http, https, ws)***
* path : path to the file ***(route)***
* description
  * client_id : sender id
  * room_id : room id

room_id = user_id:user_id
':' 구분자를 통해서 유저 아이디끼리 연결

receive_json
- Date.now() : unix time
- message
- user_id


## 실행방법

---

### 환경변수 입력

`.env.sample` 파일을 `.env` 파일로 복사 후 환경변수 입력

### 실행
```
docker-compose up -d
```