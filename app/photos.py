"""Фото мероприятий и секций: хранилище на диске, проверка файла, адрес фото (#18098, #18103)."""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Literal, Protocol, overload

from fastapi import Depends, Request, UploadFile
from tusumba_common import ApiError

MAX_SIZE = 5 * 1024 * 1024
MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

FILE_INVALID = (422, "file_invalid", "Файл не соответствует требованиям.")
PHOTO_NOT_FOUND = (404, "photo_not_found", "Фото не найдено.")

Owner = Literal["events", "clubs"]


class PhotoStorage(Protocol):
    """Где лежат файлы фото. Путь - строка вида events/{id}/{имя}.jpg, её хранит база."""

    async def save(self, path: str, content: bytes) -> None: ...

    async def read(self, path: str) -> bytes | None: ...

    async def delete(self, path: str) -> None: ...


class DiskPhotoStorage:
    """Файлы в каталоге на диске сервера (PHOTOS_DIR)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, path: str, content: bytes) -> None:
        await asyncio.to_thread(self._write, self._root / path, content)

    async def read(self, path: str) -> bytes | None:
        try:
            return await asyncio.to_thread((self._root / path).read_bytes)
        except FileNotFoundError:
            return None

    async def delete(self, path: str) -> None:
        await asyncio.to_thread((self._root / path).unlink, missing_ok=True)

    @staticmethod
    def _write(file: Path, content: bytes) -> None:
        # Сначала во временный файл: оборванная запись не оставит битое фото под рабочим именем.
        file.parent.mkdir(parents=True, exist_ok=True)
        partial = file.with_name(file.name + ".part")
        partial.write_bytes(content)
        partial.replace(file)


def get_photo_storage(request: Request) -> PhotoStorage:
    storage: PhotoStorage = request.app.state.photo_storage
    return storage


Photos = Annotated[PhotoStorage, Depends(get_photo_storage)]


def _extension(content: bytes) -> str | None:
    """Тип по сигнатуре файла: Content-Type и имя файла задаёт клиент, им не верим."""
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    return None


async def read_photo(file: UploadFile) -> tuple[bytes, str]:
    """Содержимое и расширение файла. Не JPEG, PNG или WEBP либо больше 5 МБ - 422."""
    content = await file.read(MAX_SIZE + 1)
    extension = _extension(content)
    if extension is None or len(content) > MAX_SIZE:
        raise ApiError(*FILE_INVALID)
    return content, extension


def new_photo_path(owner: Owner, object_id: uuid.UUID, extension: str) -> str:
    # Новое имя на каждую загрузку: старые версии секции ссылаются на свои файлы.
    return f"{owner}/{object_id}/{uuid.uuid4().hex}{extension}"


@overload
def photo_url(owner: Owner, object_id: uuid.UUID, path: str) -> str: ...


@overload
def photo_url(owner: Owner, object_id: uuid.UUID, path: str | None) -> str | None: ...


def photo_url(owner: Owner, object_id: uuid.UUID, path: str | None) -> str | None:
    """Адрес фото через шлюз; v меняется вместе с файлом, чтобы клиент не показал старое из кеша."""
    if path is None:
        return None
    return f"/v1/{owner}/{object_id}/photo?v={Path(path).stem}"


def media_type(path: str) -> str:
    return MEDIA_TYPES[Path(path).suffix]
