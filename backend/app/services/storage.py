from abc import ABC, abstractmethod
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import aiofiles
from datetime import datetime

from app.core.config import get_settings


class StorageManager(ABC):
    @abstractmethod
    async def upload(self, path: str, content: bytes) -> str:
        pass

    @abstractmethod
    async def download(self, path: str) -> bytes:
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        pass


class LocalStorageManager(StorageManager):
    def __init__(self, base_path: str = "./data/uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        return self.base_path / path

    async def upload(self, path: str, content: bytes) -> str:
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return str(full_path)

    async def download(self, path: str) -> bytes:
        full_path = self._get_full_path(path)

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        full_path = self._get_full_path(path)

        try:
            full_path.unlink()
            return True
        except FileNotFoundError:
            return False

    async def exists(self, path: str) -> bool:
        return self._get_full_path(path).exists()

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        return str(self._get_full_path(path))


class S3StorageManager(StorageManager):
    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client("s3", region_name=region)

    async def upload(self, path: str, content: bytes) -> str:
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=path,
                Body=content
            )
            return f"s3://{self.bucket_name}/{path}"
        except ClientError as e:
            raise Exception(f"S3 upload failed: {str(e)}")

    async def download(self, path: str) -> bytes:
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=path
            )
            return response["Body"].read()
        except ClientError as e:
            raise Exception(f"S3 download failed: {str(e)}")

    async def delete(self, path: str) -> bool:
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=path
            )
            return True
        except ClientError:
            return False

    async def exists(self, path: str) -> bool:
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=path
            )
            return True
        except ClientError:
            return False

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        try:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": path},
                ExpiresIn=expires_in
            )
        except ClientError as e:
            raise Exception(f"Presigned URL generation failed: {str(e)}")


def get_storage_manager() -> StorageManager:
    settings = get_settings()

    if settings.storage_provider == "s3":
        return S3StorageManager(
            bucket_name=settings.s3_bucket_name,
            region=settings.aws_region
        )
    else:
        return LocalStorageManager(base_path=settings.storage_path)


storage_manager = get_storage_manager()


def generate_file_path(user_id: str, chat_id: str, doc_id: str, filename: str) -> str:
    now = datetime.utcnow()
    return f"{now.year}/{now.month:02d}/{now.day:02d}/{user_id}/chats/{chat_id}/{doc_id}/{filename}"
