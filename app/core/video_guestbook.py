"""Enregistrement vidéo avec son, limité dans le temps et rangé par soirée."""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from ..config import Config

log = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 15
MIN_FREE_SPACE_BYTES = 200 * 1024 * 1024
VIDEO_FPS = 20
VIDEO_BITRATE = 6_000_000  # le défaut PyAV (200 kbit/s) pixelise fortement une image 1080p
AUDIO_RATE = 48_000
AUDIO_CHANNELS = 1


def event_folder(config: Config, event_id: str) -> Path:
    """Dossier non nominatif des vidéos d'une soirée."""
    if not event_id or any(char not in "0123456789abcdef" for char in event_id.casefold()):
        raise ValueError("Identifiant de soirée invalide")
    return config.base_dir / "livre-or" / event_id


def list_recordings(config: Config, event_id: str) -> list[Path]:
    folder = event_folder(config, event_id)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.mp4"), key=lambda path: path.stat().st_mtime)


def delete_recordings(config: Config, event_id: str) -> int:
    """Supprime les vidéos et fichiers temporaires appartenant à la soirée choisie."""
    folder = event_folder(config, event_id)
    if not folder.is_dir():
        return 0
    removed = 0
    for path in folder.iterdir():
        if path.is_file() and path.suffix.casefold() in {".mp4", ".avi", ".wav", ".tmp"}:
            path.unlink()
            removed += 1
    try:
        folder.rmdir()
    except OSError:
        pass
    return removed


class VideoGuestbookRecorder(QThread):
    """Écrit des images issues de la caméra partagée et un micro, puis les réunit en MP4."""

    remaining = pyqtSignal(int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, frame_source, destination: Path, parent=None) -> None:
        super().__init__(parent)
        self._frame_source = frame_source
        self._destination = destination
        self._stop_requested = threading.Event()

    def stop_recording(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            self.failed.emit(self._friendly_error(exc))
            return

        folder = self._destination.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(folder).free < MIN_FREE_SPACE_BYTES:
                self.failed.emit("Espace disque insuffisant pour enregistrer le message vidéo.")
                return
        except OSError as exc:
            log.exception("Accès au stockage du livre d'or impossible")
            self.failed.emit(f"Impossible d'accéder au dossier du livre d'or : {exc}")
            return

        token = uuid.uuid4().hex
        raw_video = folder / f".{token}.avi"
        audio_chunks: list[np.ndarray] = []
        audio_lock = threading.Lock()
        writer = None
        stream = None
        frame_count = 0
        started = time.monotonic()
        last_remaining = None

        def on_audio(indata, _frames, _time_info, status) -> None:
            if status:
                log.warning("État du microphone pendant l'enregistrement : %s", status)
            with audio_lock:
                audio_chunks.append(indata.copy())

        try:
            stream = sd.InputStream(samplerate=AUDIO_RATE, channels=AUDIO_CHANNELS,
                                    dtype="int16", callback=on_audio)
            stream.start()
            started = time.monotonic()
            next_frame = started
            deadline = started + MAX_DURATION_SECONDS
            while not self._stop_requested.is_set() and time.monotonic() < deadline:
                frame = self._frame_source()
                if frame is not None:
                    if writer is None:
                        height, width = frame.shape[:2]
                        writer = cv2.VideoWriter(
                            str(raw_video), cv2.VideoWriter_fourcc(*"MJPG"), VIDEO_FPS, (width, height))
                        if not writer.isOpened():
                            raise RuntimeError("Impossible d'initialiser l'enregistrement vidéo.")
                    writer.write(frame)
                    frame_count += 1
                remaining = max(0, int(deadline - time.monotonic() + 0.999))
                if remaining != last_remaining:
                    self.remaining.emit(remaining)
                    last_remaining = remaining
                next_frame += 1 / VIDEO_FPS
                self._stop_requested.wait(max(0.0, next_frame - time.monotonic()))
            if writer is None or frame_count < VIDEO_FPS:
                raise RuntimeError("La caméra n'a pas fourni assez d'images pour enregistrer la vidéo.")
        except Exception as exc:
            log.exception("Enregistrement du livre d'or vidéo impossible")
            try:
                raw_video.unlink(missing_ok=True)
            except OSError:
                log.warning("Fichier vidéo temporaire à nettoyer plus tard : %s", raw_video)
            self.failed.emit(self._friendly_error(exc))
            return
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    log.exception("Arrêt du microphone impossible")
            if writer is not None:
                writer.release()

        try:
            with audio_lock:
                samples = np.concatenate(audio_chunks, axis=0) if audio_chunks else np.empty((0, 1), dtype=np.int16)
            if len(samples) < AUDIO_RATE // 2:
                raise RuntimeError("Aucun son exploitable n'a été capté. Vérifie le microphone.")
            self._mux_mp4(raw_video, samples)
            raw_video.unlink(missing_ok=True)
            self.completed.emit(str(self._destination))
        except Exception as exc:
            log.exception("Finalisation du livre d'or vidéo impossible")
            self._destination.unlink(missing_ok=True)
            raw_video.unlink(missing_ok=True)
            self.failed.emit(self._friendly_error(exc))

    def _mux_mp4(self, raw_video: Path, samples: np.ndarray) -> None:
        import av

        with av.open(str(raw_video), "r") as source, av.open(str(self._destination), "w") as output:
            source_video = source.streams.video[0]
            video_stream = output.add_stream("mpeg4", rate=VIDEO_FPS)
            video_stream.width = source_video.width
            video_stream.height = source_video.height
            video_stream.pix_fmt = "yuv420p"
            video_stream.codec_context.bit_rate = VIDEO_BITRATE
            video_stream.codec_context.max_bit_rate = VIDEO_BITRATE
            log.info("Finalisation du livre d'or : %dx%d à %d kbit/s",
                     video_stream.width, video_stream.height, VIDEO_BITRATE // 1000)
            audio_stream = output.add_stream("aac", rate=AUDIO_RATE)
            audio_stream.layout = "mono"
            for index, frame in enumerate(source.decode(video=0)):
                frame = frame.reformat(width=video_stream.width, height=video_stream.height, format="yuv420p")
                frame.pts = index
                frame.time_base = Fraction(1, VIDEO_FPS)
                for packet in video_stream.encode(frame):
                    output.mux(packet)
            for packet in video_stream.encode(None):
                output.mux(packet)

            sample_offset = 0
            for offset in range(0, len(samples), 1024):
                chunk = samples[offset:offset + 1024, 0]
                if len(chunk) < 1024:
                    chunk = np.pad(chunk, (0, 1024 - len(chunk)))
                audio_frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
                audio_frame.sample_rate = AUDIO_RATE
                audio_frame.pts = sample_offset
                audio_frame.time_base = Fraction(1, AUDIO_RATE)
                sample_offset += min(1024, len(samples) - offset)
                for packet in audio_stream.encode(audio_frame):
                    output.mux(packet)
            for packet in audio_stream.encode(None):
                output.mux(packet)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, (OSError, RuntimeError)):
            return str(exc)
        return "Microphone indisponible ou format vidéo incompatible. Vérifie les périphériques et réessaie."
