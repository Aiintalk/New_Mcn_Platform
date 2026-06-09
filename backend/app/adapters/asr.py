"""
ASR Adapter — MCN M1 Placeholder

This module will handle Automatic Speech Recognition (audio/video transcription).
All methods raise NotImplementedError until Sprint 1 implementation.
"""


async def transcribe(
    audio_url: str,
    language: str = "zh",
    task_id: int | None = None,
) -> str:
    """
    Transcribe audio/video content to text via the ASR service.

    Args:
        audio_url: URL or file path of the audio/video to transcribe.
        language: BCP-47 language code (e.g. "zh", "en").
        task_id: Associated task ID for logging purposes.

    Returns:
        The transcribed text string.

    Raises:
        NotImplementedError: Not yet implemented.
    """
    raise NotImplementedError("asr.transcribe is not implemented in Sprint 0")
