from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from pydantic import BaseModel
from sqlalchemy import JSON as SAJSON
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

try:
    import oss2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    oss2 = None

from .storage_config import (
    CacheArchiveConfig,
    LocalCacheConfig,
    MediaStorageConfig,
    RemoteDatabaseConfig,
    StorageConfig,
)
from .state import WordMemoryResult

logger = logging.getLogger(__name__)


class LocalCacheStorage:
    def __init__(self, config: LocalCacheConfig):
        self.config = config
        self.base_dir = Path(config.directory).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max(1, config.max_entries)

    def save(self, payload: Dict[str, Any]) -> None:
        timestamp = datetime.utcnow().isoformat()
        record = dict(payload)
        record.setdefault("cached_at", timestamp)
        record.setdefault("record_id", f"{int(time.time() * 1000)}-{uuid.uuid4().hex}.json")

        session_id = payload["session_id"]
        records = self._read_session_records(session_id)
        if not records:
            legacy = self.load_legacy_records(session_id, self.max_entries)
            if legacy:
                records = list(reversed(legacy))
        records.append(record)

        records = self._sort_records(records)
        if len(records) > self.max_entries:
            records = records[:self.max_entries]
        records = list(reversed(records))

        session_payload = {
            "session_id": session_id,
            "updated_at": timestamp,
            "records": records,
        }
        target_path = self._session_path(session_id)
        target_path.write_text(json.dumps(session_payload, ensure_ascii=False), encoding="utf-8")

    def load_records(self, session_id: str, limit: int) -> list[Dict[str, Any]]:
        records = self._read_session_records(session_id)
        if not records:
            return []
        ordered = self._sort_records(records)
        return ordered[:limit]

    def load_record(self, session_id: str, record_id: str) -> Optional[Dict[str, Any]]:
        records = self._read_session_records(session_id)
        for record in records:
            if record.get("record_id") == record_id:
                return record
        return None

    def merge_records(self, session_id: str, incoming: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        if not incoming:
            return []
        timestamp = datetime.utcnow().isoformat()
        records = self._read_session_records(session_id)
        known_ids = {record.get("record_id") for record in records if record.get("record_id")}
        for record in incoming:
            record.setdefault("cached_at", timestamp)
            record_id = record.get("record_id")
            if not record_id:
                record_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex}.json"
                record["record_id"] = record_id
            if record_id in known_ids:
                continue
            known_ids.add(record_id)
            records.append(record)

        records = self._sort_records(records)
        if len(records) > self.max_entries:
            records = records[:self.max_entries]
        records = list(reversed(records))
        session_payload = {
            "session_id": session_id,
            "updated_at": timestamp,
            "records": records,
        }
        self._session_path(session_id).write_text(
            json.dumps(session_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return records

    def list_session_ids(self, max_sessions: int = 1000) -> list[str]:
        ids: Set[str] = set()
        for path in self.base_dir.glob("*.json"):
            session_id = self._read_session_id(path)
            if session_id:
                ids.add(session_id)
            if len(ids) >= max_sessions:
                break
        return sorted(ids)

    def load_legacy_records(self, session_id: str, limit: int) -> list[Dict[str, Any]]:
        pattern = f"{session_id}-*.json"
        files = sorted(
            [p for p in self.base_dir.glob(pattern) if p.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        result: list[Dict[str, Any]] = []
        for path in files[:limit]:
            record = self._load_record_file(path)
            if record:
                normalized = self._normalize_record(record)
                if normalized:
                    result.append(normalized)
        return result

    def load_legacy_record_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        path = self.base_dir / record_id
        if not path.exists():
            return None
        record = self._load_record_file(path)
        if not record:
            return None
        normalized = self._normalize_record(record)
        return normalized or None

    def _session_path(self, session_id: str) -> Path:
        safe_session = self._sanitize_storage_key(session_id)
        return self.base_dir / f"{safe_session}.json"

    @staticmethod
    def _sanitize_storage_key(value: str) -> str:
        sanitized = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
        return sanitized or "session"

    def _read_session_records(self, session_id: str) -> list[Dict[str, Any]]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, dict):
            records = data.get("records")
            if not isinstance(records, list):
                return []
            normalized: list[Dict[str, Any]] = []
            for item in records:
                if isinstance(item, dict):
                    record = self._normalize_record(item)
                    if record:
                        normalized.append(record)
            return normalized
        if isinstance(data, list):
            normalized: list[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    record = self._normalize_record(item)
                    if record:
                        normalized.append(record)
            return normalized
        return []

    def _read_session_id(self, path: Path) -> Optional[str]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            session_id = data.get("session_id")
            if isinstance(session_id, str) and session_id:
                return session_id
        if isinstance(data, dict) and "request" in data and "session_id" in data:
            session_id = data.get("session_id")
            if isinstance(session_id, str) and session_id:
                return session_id
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    session_id = item.get("session_id")
                    if isinstance(session_id, str) and session_id:
                        return session_id
        return path.stem or None

    def _load_record_file(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(record, dict):
            record.setdefault("record_id", path.name)
            return record
        return None

    @staticmethod
    def _parse_json_if_needed(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        response = record.get("response")
        response = self._parse_json_if_needed(response)
        if isinstance(response, dict):
            final_output = response.get("final_output")
            final_output = self._parse_json_if_needed(final_output)
            response["final_output"] = final_output
            record["response"] = response
        request = record.get("request")
        request = self._parse_json_if_needed(request)
        if isinstance(request, dict):
            record["request"] = request
        return record

    @staticmethod
    def _sort_records(records: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        indexed = list(enumerate(records))

        def sort_key(item: tuple[int, Dict[str, Any]]) -> tuple[str, int]:
            idx, record = item
            cached_at = record.get("cached_at")
            return (cached_at if isinstance(cached_at, str) else "", idx)

        ordered = sorted(indexed, key=sort_key, reverse=True)
        return [record for _, record in ordered]


class DatabaseStorage:
    def __init__(self, config: RemoteDatabaseConfig):
        if not config.url:
            raise ValueError("Database URL is required when remote database storage is enabled.")
        self.engine = create_engine(config.url, future=True)
        self.metadata = MetaData()
        json_type = SAJSON().with_variant(JSONB, "postgresql")
        self.table = Table(
            config.table_name,
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("session_id", String(128), index=True, nullable=False),
            Column("created_at", DateTime(timezone=True), server_default=func.now()),
            Column("request_payload", json_type, nullable=False),
            Column("response_payload", json_type, nullable=False),
        )
        self.metadata.create_all(self.engine, checkfirst=True)

    def save(self, payload: Dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                self.table.insert().values(
                    session_id=payload["session_id"],
                    created_at=datetime.utcnow(),
                    request_payload=payload["request"],
                    response_payload=payload["response"],
                )
            )


class AliyunOSSStorage:
    def __init__(self, config: MediaStorageConfig | CacheArchiveConfig):
        if oss2 is None:
            raise RuntimeError("oss2 package is required for Aliyun OSS media storage.")
        if not all([config.bucket, config.endpoint, config.access_key_id, config.access_key_secret]):
            raise ValueError("Aliyun OSS storage is missing required configuration.")

        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        self.bucket_name = config.bucket
        self.endpoint = config.endpoint
        self.prefix = config.prefix.strip("/")
        self.bucket = oss2.Bucket(auth, config.endpoint, config.bucket)

    def upload_from_url(self, url: str, category: str) -> Optional[str]:
        if not url:
            return None
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except Exception as exc:  # pragma: no cover - network errors handled at runtime
            logger.warning("Failed to download media [%s]: %s", url, exc)
            return None

        suffix = Path(urlparse(url).path).suffix or ".bin"
        key = f"{self.prefix}/{category}/{uuid.uuid4().hex}{suffix}"
        try:
            self.bucket.put_object(key, data)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to upload media to OSS: %s", exc)
            return None

        sanitized_endpoint = self.endpoint.replace("https://", "").replace("http://", "")
        return f"https://{self.bucket_name}.{sanitized_endpoint}/{key}"

    def upload_bytes(self, key: str, data: bytes) -> None:
        self.bucket.put_object(key, data)

    def list_object_keys(self, prefix: str, max_keys: int = 100) -> list[str]:
        result = self.bucket.list_objects(prefix=prefix, max_keys=max_keys)
        return [obj.key for obj in result.object_list or []]

    def download_object(self, key: str) -> Optional[bytes]:
        try:
            result = self.bucket.get_object(key)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to download object %s: %s", key, exc)
            return None
        return result.read()


class StorageManager:
    def __init__(self):
        self._local_cache_instances: Dict[str, LocalCacheStorage] = {}
        self._db_instances: Dict[str, DatabaseStorage] = {}
        self._media_instances: Dict[str, AliyunOSSStorage] = {}
        self._archive_instances: Dict[str, AliyunOSSStorage] = {}

    async def mirror_media_if_needed(
        self,
        final_output: Optional[WordMemoryResult],
        media_config: MediaStorageConfig,
        session_id: Optional[str] = None,
    ) -> Optional[WordMemoryResult]:
        if not final_output or not media_config.enable or media_config.provider == "none":
            return final_output

        if media_config.provider == "aliyun_oss":
            try:
                client = self._get_media_storage(media_config)
            except Exception as exc:
                logger.warning("Media storage unavailable: %s", exc)
                return final_output

            updated = final_output.model_copy(deep=True)
            media = updated.media
            if not media:
                return updated

            if media.image and media.image.url:
                new_url = await asyncio.to_thread(client.upload_from_url, media.image.url, "images")
                if new_url:
                    media.image.url = new_url

            if media.audio and media.audio.url:
                new_url = await asyncio.to_thread(client.upload_from_url, media.audio.url, "audio")
                if new_url:
                    media.audio.url = new_url

            return updated

        if media_config.provider == "local_fs":
            return await asyncio.to_thread(
                self._cache_media_locally,
                final_output,
                media_config,
                session_id,
            )

        return final_output

    async def persist_response(
        self,
        *,
        session_id: str,
        request_payload: Any,
        response_payload: BaseModel,
        storage_config: StorageConfig,
    ) -> None:
        serialized_request = self._to_dict(request_payload)
        serialized_response = self._to_dict(response_payload)
        record = {
            "session_id": session_id,
            "request": serialized_request,
            "response": serialized_response,
        }

        tasks = []
        if storage_config.local_cache.enable:
            local_cache = self._get_local_cache(storage_config.local_cache)
            tasks.append(asyncio.to_thread(local_cache.save, record))

        remote_db_cfg = storage_config.remote_database
        if remote_db_cfg.enable and remote_db_cfg.url:
            db_store = self._get_database_storage(remote_db_cfg)
            tasks.append(asyncio.to_thread(self._safe_db_write, db_store, record))

        archive_cfg = storage_config.archive
        if archive_cfg.enable and archive_cfg.provider == "aliyun_oss":
            archive_store = self._get_archive_storage(archive_cfg)
            tasks.append(asyncio.to_thread(self._upload_archive_record, archive_store, archive_cfg, record))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _get_local_cache(self, config: LocalCacheConfig) -> LocalCacheStorage:
        key = str(Path(config.directory).expanduser().resolve())
        if key not in self._local_cache_instances:
            self._local_cache_instances[key] = LocalCacheStorage(config)
        return self._local_cache_instances[key]

    def _get_database_storage(self, config: RemoteDatabaseConfig) -> DatabaseStorage:
        key = f"{config.url}:{config.table_name}"
        if key not in self._db_instances:
            self._db_instances[key] = DatabaseStorage(config)
        return self._db_instances[key]

    def _get_media_storage(self, config: MediaStorageConfig) -> AliyunOSSStorage:
        key = f"{config.bucket}:{config.endpoint}:{config.prefix}"
        if key not in self._media_instances:
            self._media_instances[key] = AliyunOSSStorage(config)
        return self._media_instances[key]

    def _get_archive_storage(self, config: CacheArchiveConfig) -> AliyunOSSStorage:
        key = f"{config.bucket}:{config.endpoint}:{config.prefix}"
        if key not in self._archive_instances:
            self._archive_instances[key] = AliyunOSSStorage(config)
        return self._archive_instances[key]

    def _cache_media_locally(
        self,
        final_output: WordMemoryResult,
        media_config: MediaStorageConfig,
        session_id: Optional[str],
    ) -> WordMemoryResult:
        updated = final_output.model_copy(deep=True)
        media = updated.media
        if not media:
            return updated

        safe_session = self.sanitize_storage_key(session_id or "session")
        base_dir = Path(media_config.local_directory).expanduser()
        target_dir = base_dir / safe_session
        target_dir.mkdir(parents=True, exist_ok=True)

        if media.image and media.image.url:
            new_url = self._download_media_to_local(media.image.url, target_dir, "image", safe_session)
            if new_url:
                media.image.url = new_url

        if media.audio and media.audio.url:
            new_url = self._download_media_to_local(media.audio.url, target_dir, "audio", safe_session)
            if new_url:
                media.audio.url = new_url
        self._cleanup_local_media(target_dir, media_config)

        return updated

    def _download_media_to_local(
        self,
        source_url: str,
        target_dir: Path,
        prefix: str,
        session_folder: str,
    ) -> Optional[str]:
        parsed = urlparse(source_url)
        if not parsed.scheme and source_url.startswith("/media/"):
            return source_url

        if parsed.scheme in {"file"}:
            source_path = Path(parsed.path)
            if not source_path.exists():
                return None
            suffix = source_path.suffix or ".bin"
            file_name = f"{prefix}-{uuid.uuid4().hex}{suffix}"
            dest_path = target_dir / file_name
            try:
                dest_path.write_bytes(source_path.read_bytes())
            except OSError as exc:
                logger.warning("Failed to copy local media %s: %s", source_url, exc)
                return None
            return f"/media/{session_folder}/{file_name}"

        if parsed.scheme not in {"http", "https"}:
            return source_url

        try:
            with urllib.request.urlopen(source_url, timeout=30) as response:
                data = response.read()
        except Exception as exc:
            logger.warning("Failed to download media [%s]: %s", source_url, exc)
            return None

        suffix = Path(parsed.path).suffix or ".bin"
        file_name = f"{prefix}-{uuid.uuid4().hex}{suffix}"
        dest_path = target_dir / file_name
        try:
            dest_path.write_bytes(data)
        except OSError as exc:
            logger.warning("Failed to save media locally (%s): %s", dest_path, exc)
            return None
        return f"/media/{session_folder}/{file_name}"

    def _cleanup_local_media(self, target_dir: Path, media_config: MediaStorageConfig) -> None:
        max_files = media_config.cleanup_max_files
        max_bytes = media_config.cleanup_max_bytes
        if not max_files and not max_bytes:
            return
        if not target_dir.exists():
            return
        files: list[tuple[Path, float, int]] = []
        for path in target_dir.glob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((path, stat.st_mtime, stat.st_size))
        if not files:
            return
        files.sort(key=lambda item: item[1])
        total_bytes = sum(item[2] for item in files)

        def over_limit() -> bool:
            if max_files and len(files) > max_files:
                return True
            if max_bytes and total_bytes > max_bytes:
                return True
            return False

        while files and over_limit():
            path, _, size = files.pop(0)
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:  # pragma: no cover - best effort cleanup
                logger.warning("Failed to delete media file %s: %s", path, exc)
                break
            total_bytes = max(0, total_bytes - size)

    @staticmethod
    def sanitize_storage_key(value: str) -> str:
        sanitized = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
        return sanitized or "session"

    @staticmethod
    def _to_dict(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, BaseModel):
            return payload.model_dump()
        if isinstance(payload, dict):
            return payload
        raise TypeError("Payload must be a Pydantic model or dict.")

    @staticmethod
    def _safe_db_write(store: DatabaseStorage, record: Dict[str, Any]) -> None:
        try:
            store.save(record)
        except SQLAlchemyError as exc:  # pragma: no cover
            logger.warning("Failed to persist record to database: %s", exc)

    @staticmethod
    def _upload_archive_record(store: AliyunOSSStorage, config: CacheArchiveConfig, record: Dict[str, Any]) -> None:
        timestamp = int(time.time() * 1000)
        file_name = record.get("record_id") or f"{record['session_id']}-{timestamp}.json"
        key = "/".join([config.prefix.strip("/"), record["session_id"], file_name]).strip("/")
        data = json.dumps(record, ensure_ascii=False).encode("utf-8")
        store.upload_bytes(key, data)

    async def load_cached_records(
        self,
        session_id: str,
        storage_config: StorageConfig,
        limit: int = 20,
    ) -> list[Dict[str, Any]]:
        records = self._load_local_records(session_id, storage_config.local_cache, limit)
        if records:
            return records

        archive_cfg = storage_config.archive
        if archive_cfg.enable and archive_cfg.provider == "aliyun_oss":
            archive_store = self._get_archive_storage(archive_cfg)
            downloaded = await asyncio.to_thread(
                self._download_archive_records,
                archive_store,
                archive_cfg,
                self._get_local_cache(storage_config.local_cache),
                session_id,
                limit,
            )
            if downloaded:
                return downloaded
        return []

    def _load_local_records(
        self,
        session_id: str,
        cache_config: LocalCacheConfig,
        limit: int,
    ) -> list[Dict[str, Any]]:
        local_cache = self._get_local_cache(cache_config)
        records = local_cache.load_records(session_id, limit)
        if records:
            return records
        return local_cache.load_legacy_records(session_id, limit)

    def _download_archive_records(
        self,
        store: AliyunOSSStorage,
        archive_config: CacheArchiveConfig,
        local_cache: LocalCacheStorage,
        session_id: str,
        limit: int,
    ) -> list[Dict[str, Any]]:
        prefix = "/".join([archive_config.prefix.strip("/"), session_id]).strip("/") + "/"
        keys = store.list_object_keys(prefix, max_keys=limit)
        if not keys:
            return []

        results: list[Dict[str, Any]] = []
        for key in keys:
            data = store.download_object(key)
            if not data:
                continue
            try:
                record = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            file_name = key.split("/")[-1]
            record.setdefault("record_id", file_name)
            results.append(record)
        if results:
            local_cache.merge_records(session_id, results)
        return results

    def _download_single_archive_record(
        self,
        store: AliyunOSSStorage,
        archive_config: CacheArchiveConfig,
        local_cache: LocalCacheStorage,
        session_id: str,
        record_id: str,
    ) -> Optional[Dict[str, Any]]:
        key = "/".join([archive_config.prefix.strip("/"), session_id, record_id]).strip("/")
        data = store.download_object(key)
        if not data:
            return None
        try:
            record = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        record.setdefault("record_id", record_id)
        local_cache.merge_records(session_id, [record])
        return record

    def list_session_ids(self, storage_config: StorageConfig, max_sessions: int = 1000) -> List[str]:
        ids: Set[str] = set()
        local_cache = self._get_local_cache(storage_config.local_cache)
        ids.update(local_cache.list_session_ids(max_sessions=max_sessions))
        if len(ids) >= max_sessions:
            return sorted(ids)

        archive_cfg = storage_config.archive
        if archive_cfg.enable and archive_cfg.provider == "aliyun_oss":
            try:
                archive_store = self._get_archive_storage(archive_cfg)
                prefix = archive_cfg.prefix.strip("/")
                oss_prefix = f"{prefix}/" if prefix else ""
                keys = archive_store.list_object_keys(oss_prefix, max_keys=max_sessions)
                for key in keys:
                    remainder = key[len(oss_prefix):] if key.startswith(oss_prefix) else key
                    parts = remainder.split("/", 1)
                    if parts and parts[0]:
                        ids.add(parts[0])
                    if len(ids) >= max_sessions:
                        break
            except Exception as exc:
                logger.warning("Failed to list archive session ids: %s", exc)

        return sorted(ids)

    async def load_record_by_id(
        self,
        session_id: str,
        record_id: str,
        storage_config: StorageConfig,
    ) -> Optional[Dict[str, Any]]:
        local_cache = self._get_local_cache(storage_config.local_cache)
        record = local_cache.load_record(session_id, record_id)
        if record:
            return record
        legacy_record = local_cache.load_legacy_record_by_id(record_id)
        if legacy_record:
            return legacy_record

        archive_cfg = storage_config.archive
        if archive_cfg.enable and archive_cfg.provider == "aliyun_oss":
            archive_store = self._get_archive_storage(archive_cfg)
            downloaded = await asyncio.to_thread(
                self._download_single_archive_record,
                archive_store,
                archive_cfg,
                local_cache,
                session_id,
                record_id,
            )
            if downloaded:
                return downloaded
        return None
