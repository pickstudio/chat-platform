from pydantic import BaseSettings, Field


class RedisSettings(BaseSettings):
    redis_host: str = Field(env="redis_host", default="localhost")
    redis_port: str = Field(env="redis_port", default="6379")
    redis_password: str = Field(env="redis_password", default="")

    class Config:
        env_file = '.env'


class Settings(BaseSettings):
    redis: RedisSettings = RedisSettings()
