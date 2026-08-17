from typing import Protocol


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


async def read_bounded_upload(
    upload: AsyncUpload,
    *,
    max_size: int,
    chunk_size: int = 64 * 1024,
) -> bytes:
    """Read no more than the configured limit plus one detection byte."""
    data = bytearray()
    try:
        while len(data) <= max_size:
            remaining = max_size + 1 - len(data)
            chunk = await upload.read(min(chunk_size, remaining))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)
    finally:
        await upload.close()
