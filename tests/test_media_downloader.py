from unittest.mock import MagicMock
from urllib3.exceptions import ProtocolError

from requests.exceptions import ConnectionError

from src.downloader.media_downloader import MediaDownloader


def _aborted():
    return ConnectionError(
        "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
    )


def test_retries_then_saves_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.downloader.media_downloader.time.sleep", lambda _s: None)
    downloader = MediaDownloader(download_dir=str(tmp_path))
    response = MagicMock()
    response.iter_content.return_value = [b"video-bytes"]
    response.raise_for_status.return_value = None
    downloader.session.get = MagicMock(side_effect=[_aborted(), response])

    items = downloader.download_media_items(
        [{"type": "video", "url": "https://cdn.example/video.mp4"}],
        "post1",
    )

    assert downloader.session.get.call_count == 2
    assert len(items) == 1
    assert items[0]["type"] == "video"
    assert (tmp_path / "post1_0.mp4").read_bytes() == b"video-bytes"


def test_falls_back_to_ytdlp_after_cdn_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("src.downloader.media_downloader.time.sleep", lambda _s: None)
    downloader = MediaDownloader(download_dir=str(tmp_path))
    downloader.session.get = MagicMock(side_effect=_aborted())
    monkeypatch.setattr(
        "src.pipeline._common.download_with_ytdlp",
        lambda url, pid, prefix="ig": [{"type": "video", "path": str(tmp_path / "fallback.mp4")}],
    )
    (tmp_path / "fallback.mp4").write_bytes(b"ok")

    items = downloader.download_media_items(
        [{"type": "video", "url": "https://cdn.example/video.mp4"}],
        "post2",
        permalink="https://www.instagram.com/p/DY-ntTWrFmF/",
    )

    assert downloader.session.get.call_count == 3
    assert items == [{"type": "video", "path": str(tmp_path / "fallback.mp4")}]


def test_protocol_error_is_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr("src.downloader.media_downloader.time.sleep", lambda _s: None)
    downloader = MediaDownloader(download_dir=str(tmp_path))
    response = MagicMock()
    response.iter_content.return_value = [b"img"]
    response.raise_for_status.return_value = None
    downloader.session.get = MagicMock(
        side_effect=[ConnectionError("x", ProtocolError("Connection aborted.", Exception())), response]
    )

    items = downloader.download_media_items(
        [{"type": "image", "url": "https://cdn.example/a.jpg"}],
        "post3",
    )
    assert len(items) == 1
    assert (tmp_path / "post3_0.jpg").read_bytes() == b"img"


def test_does_not_ytdlp_when_cdn_works(tmp_path, monkeypatch):
    downloader = MediaDownloader(download_dir=str(tmp_path))
    response = MagicMock()
    response.iter_content.return_value = [b"ok"]
    response.raise_for_status.return_value = None
    downloader.session.get = MagicMock(return_value=response)
    called = {"n": 0}

    def boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("yt-dlp should not run")

    monkeypatch.setattr("src.pipeline._common.download_with_ytdlp", boom)

    items = downloader.download_media_items(
        [{"type": "video", "url": "https://cdn.example/video.mp4"}],
        "post4",
        permalink="https://www.instagram.com/p/abc/",
    )
    assert called["n"] == 0
    assert len(items) == 1
