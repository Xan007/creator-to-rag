from src.analyzer.media_optimize import (
    max_video_height,
    prepare_for_gemini,
    should_transcode,
    ytdlp_format,
)


def test_ytdlp_format_caps_height(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_MAX_HEIGHT", "720")
    assert "height<=720" in ytdlp_format()


def test_images_are_not_transcoded():
    item = {"type": "image", "path": "slide.jpg"}
    assert prepare_for_gemini(item) is item or prepare_for_gemini(item) == item


def test_should_transcode_skips_small_720p(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_OPTIMIZE", "true")
    monkeypatch.setattr("src.analyzer.media_optimize.shutil.which", lambda name: "ffmpeg")
    monkeypatch.setattr(
        "src.analyzer.media_optimize.probe_video",
        lambda path: (720, 3 * 1024 * 1024),
    )
    assert should_transcode("reel.mp4") is False


def test_should_transcode_tall_or_heavy_video(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_OPTIMIZE", "true")
    monkeypatch.setattr("src.analyzer.media_optimize.shutil.which", lambda name: "ffmpeg")
    monkeypatch.setattr(
        "src.analyzer.media_optimize.probe_video",
        lambda path: (1920, 40 * 1024 * 1024),
    )
    assert should_transcode("reel.mp4") is True


def test_optimize_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_OPTIMIZE", "false")
    monkeypatch.setattr("src.analyzer.media_optimize.shutil.which", lambda name: "ffmpeg")
    assert should_transcode("reel.mp4") is False


def test_max_height_floor(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_MAX_HEIGHT", "240")
    assert max_video_height() == 360
