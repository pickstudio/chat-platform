from pydantic import BaseSettings, Field


class RedisSettings(BaseSettings):
    redis_host: str = Field(env="redis_host", default="localhost")
    redis_port: str = Field(env="redis_port", default="6379")
    redis_password: str = Field(env="redis_password", default="")

    class Config:
        env_file = '.env.prod'


class BotoSettings(BaseSettings):
    aws_access_key_id: str = Field(env="aws_access_key_id", default="")
    aws_secret_access_key: str = Field(env="aws_secret_access_key", default="")
    region_name: str = Field(env="region_name", default="ap-northeast-2")

    class Config:
        env_file = '.env.prod'


class Settings(BaseSettings):
    redis: RedisSettings = RedisSettings()
    boto3: BotoSettings = BotoSettings()
