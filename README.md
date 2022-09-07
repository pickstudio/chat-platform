# Chat Platform
```
service --> http --> user session
service --> ws --> pub/sub --> http --> push
```

## OpenAPI Docs
아래의 경로를 통해 API 명세 확인 가능
```
path : /docs
       /redoc
```

## Getting Started

### Set environment
1. `.env` 생성
```
cp .env.sample .env 
```

2. 설정
* `.env`파일에 환경변수 입력

3. 실행
```
docker-compose up
docker-compose up -d (background)
```
