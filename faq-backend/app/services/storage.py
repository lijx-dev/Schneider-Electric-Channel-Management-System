"""Storage backend abstraction for avatar uploads."""
from __future__ import annotations

import os
import re
import uuid
from urllib.parse import parse_qs, quote, unquote, urlsplit

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

LOCAL_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../static/avatars")


class StorageService:
    AVATAR_PROXY_PATH = "/api/upload/avatar/view"

    @staticmethod
    def upload_avatar(
        content: bytes,
        extension: str,
        user_id: str,
        content_type: str,
        display_name: str = "",
        phone: str = "",
    ) -> str:
        backend = settings.storage_backend
        if backend == "cos":
            return StorageService._upload_to_cos(content, extension, user_id, content_type, display_name, phone)

        if settings.is_production:
            raise RuntimeError("生产环境不允许使用本地文件系统存储头像")

        return StorageService._upload_to_local(content, extension)

    @staticmethod
    def _upload_to_local(content: bytes, extension: str) -> str:
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        safe_filename = f"avatar_{uuid.uuid4().hex[:12]}.{extension}"
        file_path = os.path.join(LOCAL_UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        logger.info("avatar_uploaded_local", filename=safe_filename)
        return f"/static/avatars/{safe_filename}"

    @staticmethod
    def _upload_to_cos(
        content: bytes,
        extension: str,
        user_id: str,
        content_type: str,
        display_name: str,
        phone: str = "",
    ) -> str:
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:
            raise RuntimeError("缺少 cos-python-sdk-v5 依赖，无法上传到对象存储") from exc

        config = CosConfig(
            Region=settings.COS_REGION,
            SecretId=settings.COS_SECRET_ID,
            SecretKey=settings.COS_SECRET_KEY,
            Token=settings.COS_SESSION_TOKEN,
            Scheme="https",
        )
        client = CosS3Client(config)

        safe_stem = StorageService._build_avatar_stem(display_name, user_id, phone)
        object_key = f"avatars/{safe_stem}-头像"
        client.put_object(
            Bucket=settings.COS_BUCKET,
            Body=content,
            Key=object_key,
            ContentType=content_type,
        )

        public_url = f"{settings.storage_public_base_url}/{object_key}"
        logger.info("avatar_uploaded_cos", bucket=settings.COS_BUCKET, key=object_key)
        return public_url

    @staticmethod
    def normalize_avatar_reference(value: str | None) -> str:
        if not value or not isinstance(value, str):
            return ""

        normalized = value.strip()
        if not normalized:
            return ""

        if normalized.startswith("cloud://"):
            return normalized

        cloud_path = StorageService.extract_cloud_file_path(normalized)
        if cloud_path and cloud_path.startswith("avatars/"):
            return cloud_path

        object_key = StorageService.extract_cos_object_key(normalized)
        if object_key:
            return object_key

        if normalized.startswith("http"):
            parsed = urlsplit(normalized)
            local_path = unquote(parsed.path or "")
            if local_path.startswith("/static/avatars/"):
                return local_path

        return normalized

    @staticmethod
    def build_avatar_access_url(value: str | None, base_url: str) -> str:
        normalized = StorageService.normalize_avatar_reference(value)
        normalized_base_url = StorageService.normalize_public_url(base_url)
        if not normalized:
            return ""

        if normalized.startswith("cloud://"):
            return normalized

        object_key = StorageService.extract_cos_object_key(normalized)
        if object_key:
            encoded_key = quote(object_key, safe="")
            return f"{normalized_base_url}{StorageService.AVATAR_PROXY_PATH}?key={encoded_key}"

        if normalized.startswith("http"):
            return StorageService.normalize_public_url(normalized)

        if normalized.startswith("/"):
            return f"{normalized_base_url}{normalized}"

        return f"{normalized_base_url}/{normalized.lstrip('/')}"

    @staticmethod
    def extract_cos_object_key(value: str | None) -> str | None:
        if not value or not isinstance(value, str):
            return None

        normalized = value.strip()
        if not normalized:
            return None

        if normalized.startswith("cos://"):
            key = normalized[6:].split("?", 1)[0].lstrip("/")
            return key or None

        cloud_path = StorageService.extract_cloud_file_path(normalized)
        if cloud_path and cloud_path.startswith("avatars/"):
            return cloud_path

        if normalized.startswith("/avatars/"):
            return normalized.lstrip("/")

        if normalized.startswith("avatars/"):
            return normalized.split("?", 1)[0]

        parsed = urlsplit(normalized)
        if parsed.path:
            parsed_key = StorageService._extract_object_key_from_proxy_query(parsed.query)
            if parsed_key and StorageService._is_avatar_proxy_path(parsed.path):
                return parsed_key

            host = (parsed.netloc or "").lower()
            path = unquote(parsed.path.lstrip("/"))
            if path.startswith("avatars/") and StorageService._is_known_cos_host(host):
                return path

        return None

    @staticmethod
    def extract_cloud_file_path(value: str | None) -> str | None:
        if not value or not isinstance(value, str):
            return None

        normalized = value.strip()
        if not normalized:
            return None

        cloud_index = normalized.find("cloud://")
        if cloud_index < 0:
            return None

        cloud_reference = normalized[cloud_index:]
        without_scheme = cloud_reference[len("cloud://") :]
        if not without_scheme:
            return None

        parts = without_scheme.split("/", 1)
        if len(parts) < 2:
            return None

        object_key = parts[1].split("?", 1)[0].strip().lstrip("/")
        return object_key or None

    @staticmethod
    def create_presigned_avatar_url(object_key: str, expires_in: int | None = None) -> str:
        normalized_key = StorageService.extract_cos_object_key(object_key)
        if not normalized_key or not normalized_key.startswith("avatars/"):
            raise RuntimeError("无效的头像对象路径")

        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:
            raise RuntimeError("缺少 cos-python-sdk-v5 依赖，无法生成头像访问地址") from exc

        config = CosConfig(
            Region=settings.COS_REGION,
            SecretId=settings.COS_SECRET_ID,
            SecretKey=settings.COS_SECRET_KEY,
            Token=settings.COS_SESSION_TOKEN,
            Scheme="https",
        )
        client = CosS3Client(config)

        expire_seconds = expires_in or settings.COS_SIGN_EXPIRE_SECONDS
        try:
            return client.get_presigned_download_url(
                Bucket=settings.COS_BUCKET,
                Key=normalized_key,
                Expired=expire_seconds,
            )
        except AttributeError:
            return client.get_presigned_url(
                Method="GET",
                Bucket=settings.COS_BUCKET,
                Key=normalized_key,
                Expired=expire_seconds,
            )

    @staticmethod
    def _build_avatar_stem(display_name: str, user_id: str, phone: str = "") -> str:
        fallback_id = f"user_{user_id[:8]}"
        phone_part = re.sub(r"\D+", "", phone or "") or fallback_id
        name_part = (display_name or "").strip() or fallback_id
        raw_name = f"{phone_part}-{name_part}"
        compact_name = re.sub(r"\s+", "", raw_name)
        safe_name = re.sub(r'[\\/:*?"<>|#%\[\]{}]+', "_", compact_name).strip("._")
        return safe_name[:100] or fallback_id

    @staticmethod
    def normalize_public_url(value: str | None) -> str:
        if not value or not isinstance(value, str):
            return ""

        normalized = value.strip().rstrip("/")
        if not normalized:
            return ""

        parsed = urlsplit(normalized)
        if parsed.scheme.lower() != "http":
            return normalized

        hostname = (parsed.hostname or "").lower()
        if StorageService._is_local_hostname(hostname):
            return normalized

        return parsed._replace(scheme="https").geturl().rstrip("/")

    @staticmethod
    def _extract_object_key_from_proxy_query(query: str) -> str | None:
        params = parse_qs(query or "")
        value = params.get("key", [""])[0].strip()
        if not value:
            return None
        return unquote(value).lstrip("/") or None

    @staticmethod
    def _is_avatar_proxy_path(path: str) -> bool:
        clean_path = (path or "").rstrip("/")
        return clean_path.endswith(StorageService.AVATAR_PROXY_PATH)

    @staticmethod
    def _is_local_hostname(host: str) -> bool:
        if not host:
            return False

        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            return True

        if host.startswith("10.") or host.startswith("192.168."):
            return True

        if re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", host):
            return True

        return host.endswith(".local")

    @staticmethod
    def _is_known_cos_host(host: str) -> bool:
        if not host:
            return False

        normalized_host = host.strip().lower()
        if normalized_host.endswith(".tcb.qcloud.la"):
            return True

        known_hosts = set()
        if settings.storage_public_base_url:
            known_hosts.add(urlsplit(settings.storage_public_base_url).netloc.lower())
        if settings.COS_BUCKET and settings.COS_REGION:
            known_hosts.add(f"{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com".lower())

        return normalized_host in known_hosts
