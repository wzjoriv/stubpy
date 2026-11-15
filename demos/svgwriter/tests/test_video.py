from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

import svgwriter as svg
from svgwriter import ops, video
from svgwriter.cli import load_scene, main
from svgwriter.video import _ffmpeg
from svgwriter.video.frames import to_frame

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not on PATH")
needs_skia = pytest.mark.skipif(not ops.available(), reason="skia-python is not installed")
WIDTH, HEIGHT = 16, 12


def png(width: int, height: int, rgba: tuple[int, int, int, int]) -> bytes:
    """A solid-color PNG built with the standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    row = b"\x00" + bytes(rgba) * width
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")


class FakeArray:
    """Minimal stand-in for a NumPy RGBA array."""

    def __init__(self, width: int, height: int, value: int, dtype: str = "uint8", channels: int = 4) -> None:
        self.shape = (height, width, channels)
        self.dtype = dtype
        self._data = bytes([value]) * (width * height * channels)

    def tobytes(self) -> bytes:
        return self._data


def solid_png(document: svg.Document, seconds: float) -> bytes:
    """Renderer used by the CLI test through ``module:function``."""
    return png(WIDTH, HEIGHT, (int(255 * min(seconds, 1.0)), 0, 0, 255))


def gray_array(document: svg.Document, seconds: float) -> FakeArray:
    return FakeArray(WIDTH, HEIGHT, int(200 * min(seconds, 1.0)))


def _doc() -> svg.Document:
    doc = svg.Document(WIDTH, HEIGHT)
    doc.circle(8, 6, 3, fill="red")
    return doc


class TestFrames:
    def test_frame_times(self) -> None:
        assert video.frame_times(4, 1) == [0, 0.25, 0.5, 0.75]
        assert len(video.frame_times(30, 0.5)) == 15
        assert video.frame_times(10, 0.01) == [0]
        with pytest.raises(ValueError, match="fps"):
            video.frame_times(0, 1)
        with pytest.raises(ValueError, match="duration"):
            video.frame_times(1, 0)

    def test_png_frames(self) -> None:
        frame = to_frame(3, 0.1, png(5, 7, (0, 0, 0, 255)))
        assert (frame.index, frame.width, frame.height, frame.png) == (3, 5, 7, True)
        assert to_frame(0, 0, bytearray(png(2, 2, (1, 2, 3, 4)))).png

    def test_array_frames(self) -> None:
        frame = to_frame(0, 0, FakeArray(4, 3, 9))
        assert (frame.width, frame.height, frame.png, len(frame.data)) == (4, 3, False, 48)

    @pytest.mark.parametrize(
        ("data", "error", "match"),
        [
            (b"not a png", TypeError, "not a PNG"),
            (FakeArray(4, 3, 0, channels=3), ValueError, "shape"),
            (FakeArray(4, 3, 0, dtype="float32"), ValueError, "uint8"),
            ("text", TypeError, "expected PNG bytes or an RGBA array"),
        ],
    )
    def test_bad_frames(self, data: object, error: type[Exception], match: str) -> None:
        with pytest.raises(error, match=match):
            to_frame(0, 0, data)  # type: ignore[arg-type]


class TestRenderers:
    def test_resolve(self) -> None:
        assert video.resolve_renderer(solid_png) is solid_png
        assert callable(video.resolve_renderer("skia"))
        assert video.resolve_renderer("tests.test_video:gray_array") is gray_array
        with pytest.raises(ValueError, match="no renderer given"):
            video.resolve_renderer(None)
        with pytest.raises(ValueError, match="unknown renderer"):
            video.resolve_renderer("nope")
        with pytest.raises(TypeError, match="not callable"):
            video.resolve_renderer("tests.test_video:WIDTH")

    def test_register(self) -> None:
        @video.register_renderer("test-solid")
        def render(document: svg.Document, seconds: float) -> bytes:
            return solid_png(document, seconds)

        assert video.resolve_renderer("test-solid") is render
        assert svg.register_renderer is video.register_renderer

    def test_iter_frames_and_update(self) -> None:
        seen: list[float] = []
        frames = list(video.iter_frames(_doc(), 4, 1, solid_png, update=lambda doc, t: seen.append(t)))
        assert [f.time for f in frames] == seen == [0, 0.25, 0.5, 0.75]

    def test_duration_from_smil(self) -> None:
        doc = _doc()
        assert video.animation_duration(doc) is None
        with pytest.raises(ValueError, match="duration"):
            list(video.iter_frames(doc, 4, None, solid_png))
        circle = doc.root.find(svg.Circle)
        assert circle is not None
        circle.append(svg.Animate(attribute_name="r", from_=3, to=5, dur=1.5, begin=0.5))
        circle.append(svg.Animate(attribute_name="cx", dur="500ms"))
        circle.append(svg.Animate(attribute_name="cy", dur="indefinite"))
        assert video.animation_duration(doc) == 2.0
        assert len(list(video.iter_frames(doc, 2, None, solid_png))) == 4


class TestFFmpegMissing:
    def test_no_op_error_before_rendering(self, tmp_path: Path) -> None:
        calls: list[float] = []

        def renderer(document: svg.Document, seconds: float) -> bytes:
            calls.append(seconds)
            return solid_png(document, seconds)

        target = tmp_path / "out.mp4"
        with pytest.raises(svg.FFmpegNotFoundError, match="Nothing was rendered"):
            _doc().render_animation(target, 10, 1, renderer, ffmpeg="definitely-not-ffmpeg-xyz")
        assert calls == [] and not target.exists()

    def test_output_arguments(self) -> None:
        assert "libx264" in _ffmpeg.output_args("a.MP4")
        assert any("palettegen" in arg for arg in _ffmpeg.output_args("a.gif"))
        assert _ffmpeg.output_args("a.mkv") == []

    def test_mixed_frame_sizes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frames = [to_frame(0, 0, png(2, 2, (0, 0, 0, 255))), to_frame(1, 0.1, png(3, 2, (0, 0, 0, 255)))]
        checked = _ffmpeg._checked(iter(frames[1:]), frames[0])
        next(checked)
        with pytest.raises(ValueError, match="frame 1 is 3x2"):
            next(checked)

    def test_no_frames(self) -> None:
        with pytest.raises(ValueError, match="no frames"):
            _ffmpeg.encode([], "x.mp4", 10, executable="ffmpeg")


@needs_ffmpeg
class TestEncoding:
    @pytest.mark.parametrize("suffix", [".mp4", ".gif", ".webm"])
    def test_png_frames_encode(self, tmp_path: Path, suffix: str) -> None:
        target = tmp_path / f"anim{suffix}"
        written = _doc().render_animation(target, fps=8, duration=0.5, renderer=solid_png)
        assert written == target and target.stat().st_size > 0

    def test_rgba_frames_encode(self, tmp_path: Path) -> None:
        target = tmp_path / "gray.mp4"
        video.render_animation(_doc(), target, 5, 1, gray_array)
        assert target.stat().st_size > 0

    def test_ffmpeg_failure_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(video.FFmpegError, match="ffmpeg exited"):
            video.render_animation(_doc(), tmp_path / "missing-dir" / "x.mp4", 5, 0.4, solid_png)

    def test_renderer_error_stops_ffmpeg(self, tmp_path: Path) -> None:
        def broken(document: svg.Document, seconds: float) -> bytes:
            if seconds > 0:
                raise RuntimeError("boom")
            return solid_png(document, seconds)

        with pytest.raises(RuntimeError, match="boom"):
            video.render_animation(_doc(), tmp_path / "x.mp4", 5, 1, broken)

    @needs_skia
    def test_skia_renderer(self, tmp_path: Path) -> None:
        target = tmp_path / "skia.gif"
        doc = _doc()
        dot = doc.root.find(svg.Circle)
        assert dot is not None

        def grow(document: svg.Document, seconds: float) -> None:
            dot.r = 2 + 4 * seconds

        doc.render_animation(target, 6, 0.5, "skia", update=grow)
        probe = subprocess.run([FFMPEG or "ffmpeg", "-i", str(target)], capture_output=True, text=True)
        assert "gif" in probe.stderr


SCENE = '''
import svgwriter as svg
FPS = 4
DURATION = 1.0
def build():
    doc = svg.Document(16, 12)
    doc.circle(8, 6, 3)
    return doc
def update(doc, t):
    doc.root.find(svg.Circle).r = 3 + t
'''


class TestAnimateCommand:
    def test_load_scene(self, tmp_path: Path) -> None:
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        doc, update, settings = load_scene(script)
        assert isinstance(doc, svg.Document) and update is not None and settings == {"fps": 4, "duration": 1.0}
        variable = tmp_path / "var.py"
        variable.write_text("import svgwriter as svg\ndocument = svg.Document(4, 4)\n", encoding="utf-8")
        assert load_scene(variable)[1] is None
        svg_file = tmp_path / "pic.svg"
        _doc().save(svg_file)
        assert load_scene(svg_file)[0].root.find(svg.Circle) is not None

    def test_bad_scene(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        script = tmp_path / "empty.py"
        script.write_text("x = 1\n", encoding="utf-8")
        assert main(["animate", str(script), "--renderer", "tests.test_video:solid_png", "-o", str(tmp_path / "a.mp4")]) == 1
        assert "must define build()" in capsys.readouterr().err

    def test_missing_ffmpeg(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        code = main(["animate", str(script), "--renderer", "tests.test_video:solid_png", "--ffmpeg", "no-such-ffmpeg-xyz"])
        assert code == 1 and "was not found" in capsys.readouterr().err

    def test_missing_renderer(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        if FFMPEG is None:
            pytest.skip("ffmpeg is checked first")
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        assert main(["animate", str(script), "-o", str(tmp_path / "a.mp4")]) == 1
        assert "no renderer given" in capsys.readouterr().err

    @needs_ffmpeg
    def test_animate(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        target = tmp_path / "out.gif"
        assert main(["animate", str(script), "--renderer", "tests.test_video:solid_png", "--out", str(target), "--fps", "6"]) == 0
        assert target.stat().st_size > 0 and str(target) in capsys.readouterr().out


class TestRenderAndOutlineCommands:
    @needs_skia
    def test_render(self, tmp_path: Path) -> None:
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        target = tmp_path / "frame.png"
        assert main(["render", str(script), "-o", str(target), "--time", "0.5", "--scale", "2", "--background", "white"]) == 0
        assert target.read_bytes().startswith(b"\x89PNG")

    @needs_skia
    def test_outline(self, tmp_path: Path) -> None:
        target = tmp_path / "hi.svg"
        assert main(["outline", "Hi", "--size", "20", "-o", str(target)]) == 0
        doc = svg.Document.from_file(target)
        path = doc.root.find(svg.Path)
        assert path is not None and path.bbox.x >= 3.9

    def test_commands_report_missing_skia(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(ops._skia, "_load", lambda: None)
        script = tmp_path / "scene.py"
        script.write_text(SCENE, encoding="utf-8")
        assert main(["render", str(script), "-o", str(tmp_path / "x.png")]) == 1
        assert main(["outline", "Hi"]) == 1
        assert capsys.readouterr().err.count("svgwriter: error: ") == 2
