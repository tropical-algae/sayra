import asyncio

from sayra.common.config import Settings
from sayra.core.exceptions import ProviderError
from sayra.core.types import AudioInput


class FFmpegAudioNormalizer:
    """Converts browser recording formats into mono 16 kHz WAV for ASR."""

    def __init__(self, config: Settings) -> None:
        self.timeout = config.AUDIO_CONVERSION_TIMEOUT_SECONDS

    async def normalize(self, audio: AudioInput) -> AudioInput:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(audio.content), timeout=self.timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ProviderError("Audio normalization timed out") from exc
        if process.returncode != 0 or not stdout:
            detail = stderr.decode("utf-8", "replace")[-1000:]
            raise ProviderError(f"Audio normalization failed: {detail}")
        return AudioInput(
            content=stdout,
            content_type="audio/wav",
            filename="normalized.wav",
        )
