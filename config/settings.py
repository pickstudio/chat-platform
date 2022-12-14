from pydantic import BaseSettings

env = ".env"


class RedisSettings(BaseSettings):
    redis_host: str
    redis_port: str
    redis_password: str


class BotoSettings(BaseSettings):
    aws_access_key_id: str
    aws_secret_access_key: str
    region_name: str


class DynamoSettings(BaseSettings):
    table_name: str


class Settings(BaseSettings):
    redis: RedisSettings = RedisSettings(_env_file=env)
    boto3: BotoSettings = BotoSettings(_env_file=env)
    dynamo: DynamoSettings = DynamoSettings(_env_file=env)
