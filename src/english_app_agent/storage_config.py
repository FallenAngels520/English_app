"""
Python-side storage configuration.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel


class LocalCacheConfig(BaseModel):
    enable: bool = True
    directory: str = os.path.expanduser("~/.english_app_agent/cache")
    max_entries: int = 200


class RemoteDatabaseConfig(BaseModel):
    enable: bool = False
    url: Optional[str] = None
    table_name: str = "chat_responses"


class MediaStorageConfig(BaseModel):
    enable: bool = False
    provider: Literal["aliyun_oss", "local_fs", "none"] = "none"
    bucket: Optional[str] = None
    endpoint: Optional[str] = None
    access_key_id: Optional[str] = None
    access_key_secret: Optional[str] = None
    prefix: str = "chat_media/"
    local_directory: str = os.path.expanduser("~/.english_app_agent/media")


class CacheArchiveConfig(BaseModel):
    enable: bool = False
    provider: Literal["aliyun_oss", "none"] = "none"
    bucket: Optional[str] = None
    endpoint: Optional[str] = None
    access_key_id: Optional[str] = None
    access_key_secret: Optional[str] = None
    prefix: str = "chat_cache/"


class StorageConfig(BaseModel):
    local_cache: LocalCacheConfig = LocalCacheConfig()
    remote_database: RemoteDatabaseConfig = RemoteDatabaseConfig()
    media: MediaStorageConfig = MediaStorageConfig()
    archive: CacheArchiveConfig = CacheArchiveConfig()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_storage_config(config: Optional[RunnableConfig]) -> StorageConfig:
    cfg = StorageConfig()
    configurable = (config or {}).get("configurable", {})

    cache_cfg = configurable.get("storage", {}).get("local_cache", {})
    cfg.local_cache = LocalCacheConfig(
        enable=_env_bool("LOCAL_CACHE_ENABLE", cache_cfg.get("enable", cfg.local_cache.enable)),
        directory=os.getenv("LOCAL_CACHE_DIR", cache_cfg.get("directory", cfg.local_cache.directory)),
        max_entries=_env_int("LOCAL_CACHE_MAX_ENTRIES", cache_cfg.get("max_entries", cfg.local_cache.max_entries)),
    )

    remote_cfg = configurable.get("storage", {}).get("remote_database", {})
    cfg.remote_database = RemoteDatabaseConfig(
        enable=_env_bool("REMOTE_DB_ENABLE", remote_cfg.get("enable", cfg.remote_database.enable)),
        url=os.getenv("REMOTE_DB_URL", remote_cfg.get("url", cfg.remote_database.url)),
        table_name=remote_cfg.get("table_name", cfg.remote_database.table_name),
    )

    media_cfg = configurable.get("storage", {}).get("media", {})
    cfg.media = MediaStorageConfig(
        enable=_env_bool("MEDIA_ENABLE", media_cfg.get("enable", cfg.media.enable)),
        provider=media_cfg.get("provider", cfg.media.provider),
        bucket=os.getenv("MEDIA_BUCKET", media_cfg.get("bucket", cfg.media.bucket)),
        endpoint=os.getenv("MEDIA_ENDPOINT", media_cfg.get("endpoint", cfg.media.endpoint)),
        access_key_id=os.getenv("MEDIA_ACCESS_KEY_ID", media_cfg.get("access_key_id", cfg.media.access_key_id)),
        access_key_secret=os.getenv(
            "MEDIA_ACCESS_KEY_SECRET", media_cfg.get("access_key_secret", cfg.media.access_key_secret)
        ),
        prefix=media_cfg.get("prefix", cfg.media.prefix),
        local_directory=os.getenv(
            "MEDIA_LOCAL_DIRECTORY",
            media_cfg.get("local_directory", cfg.media.local_directory),
        ),
    )

    archive_cfg = configurable.get("storage", {}).get("archive", {})
    cfg.archive = CacheArchiveConfig(
        enable=_env_bool("ARCHIVE_ENABLE", archive_cfg.get("enable", cfg.archive.enable)),
        provider=archive_cfg.get("provider", cfg.archive.provider),
        bucket=os.getenv("ARCHIVE_BUCKET", archive_cfg.get("bucket", cfg.archive.bucket)),
        endpoint=os.getenv("ARCHIVE_ENDPOINT", archive_cfg.get("endpoint", cfg.archive.endpoint)),
        access_key_id=os.getenv(
            "ARCHIVE_ACCESS_KEY_ID", archive_cfg.get("access_key_id", cfg.archive.access_key_id)
        ),
        access_key_secret=os.getenv(
            "ARCHIVE_ACCESS_KEY_SECRET", archive_cfg.get("access_key_secret", cfg.archive.access_key_secret)
        ),
        prefix=archive_cfg.get("prefix", cfg.archive.prefix),
    )

    return cfg
