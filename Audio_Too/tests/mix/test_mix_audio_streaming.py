"""Tests for range-based audio file streaming logic."""

from __future__ import annotations

from io import BytesIO

from app.media_streaming import send_audio_file_range


class MockWFile(BytesIO):
    def flush(self) -> None:
        pass


class MockStreamingHandler:
    def __init__(self, range_header: str | None = None):
        self.headers = {}
        if range_header:
            self.headers["Range"] = range_header
        self.response_status = None
        self.response_headers = {}
        self.wfile = MockWFile()

    def send_response(self, status: int) -> None:
        self.response_status = status

    def send_header(self, keyword: str, value: str) -> None:
        self.response_headers[keyword] = value

    def end_headers(self) -> None:
        pass


def test_send_audio_file_range_whole(tmp_path) -> None:
    file_path = tmp_path / "test.wav"
    file_content = b"abcdefghijklmnopqrstuvwxyz"
    file_path.write_bytes(file_content)

    handler = MockStreamingHandler()
    send_audio_file_range(handler, file_path)

    assert handler.response_status == 200
    assert handler.response_headers["Content-Length"] == str(len(file_content))
    assert handler.response_headers["Accept-Ranges"] == "bytes"
    assert handler.wfile.getvalue() == file_content


def test_send_audio_file_range_partial(tmp_path) -> None:
    file_path = tmp_path / "test.wav"
    file_content = b"abcdefghijklmnopqrstuvwxyz"
    file_path.write_bytes(file_content)

    # Request range 2-10 (inclusive)
    handler = MockStreamingHandler("bytes=2-10")
    send_audio_file_range(handler, file_path)

    assert handler.response_status == 206
    assert handler.response_headers["Content-Range"] == f"bytes 2-10/{len(file_content)}"
    assert handler.response_headers["Content-Length"] == str(10 - 2 + 1)
    assert handler.wfile.getvalue() == file_content[2:11]


def test_send_audio_file_range_invalid_start(tmp_path) -> None:
    file_path = tmp_path / "test.wav"
    file_content = b"abcdefghijklmnopqrstuvwxyz"
    file_path.write_bytes(file_content)

    # Request range start exceeding file size
    handler = MockStreamingHandler("bytes=50-60")
    send_audio_file_range(handler, file_path)

    assert handler.response_status == 416
    assert handler.response_headers["Content-Range"] == f"bytes */{len(file_content)}"


def test_send_audio_file_range_not_found(tmp_path) -> None:
    file_path = tmp_path / "non_existent.wav"
    handler = MockStreamingHandler()
    send_audio_file_range(handler, file_path)

    assert handler.response_status == 404
