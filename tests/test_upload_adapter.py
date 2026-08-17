import asyncio

from app.web.upload_adapter import read_bounded_upload


class FakeUpload:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0
        self.closed = False
        self.bytes_returned = 0

    async def read(self, size: int = -1) -> bytes:
        end = len(self.data) if size < 0 else self.position + size
        chunk = self.data[self.position : end]
        self.position += len(chunk)
        self.bytes_returned += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


def test_bounded_upload_reads_only_limit_plus_one_and_closes() -> None:
    upload = FakeUpload(b"x" * 100)

    data = asyncio.run(read_bounded_upload(upload, max_size=10, chunk_size=4))

    assert data == b"x" * 11
    assert upload.bytes_returned == 11
    assert upload.closed is True


def test_bounded_upload_closes_when_read_fails() -> None:
    class FailingUpload(FakeUpload):
        async def read(self, size: int = -1) -> bytes:
            raise OSError("private internal detail")

    upload = FailingUpload(b"")

    try:
        asyncio.run(read_bounded_upload(upload, max_size=10))
    except OSError:
        pass

    assert upload.closed is True
