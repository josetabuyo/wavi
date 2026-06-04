"""
Audio transcription via Groq API (whisper-large-v3), with local pywhispercpp fallback.
GROQ_API_KEY is read from the environment; call load_dotenv() in your entry point.
"""
import os
import sys
from pathlib import Path

_local_model = None  # module-level singleton — loaded once on first use


async def transcribe(audio_path: str | Path) -> str | None:
    """Returns transcript string, or None if all methods fail."""
    try:
        return await _transcribe_groq(audio_path)
    except Exception as e:
        print(f"[wavi] Groq transcription failed ({e}), trying local fallback", file=sys.stderr)
    try:
        return _transcribe_local(audio_path)
    except Exception as e:
        print(f"[wavi] Local transcription failed ({e})", file=sys.stderr)
        return None


async def _transcribe_groq(audio_path: str | Path) -> str:
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    client = Groq(api_key=api_key)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3", file=f, language="es"
        )
    return result.text


def _transcribe_local(audio_path: str | Path) -> str:
    global _local_model
    try:
        from pywhispercpp.model import Model
        if _local_model is None:
            _local_model = Model("small", n_threads=4)
        segments = _local_model.transcribe(str(audio_path))
        return " ".join(s.text for s in segments)
    except ImportError:
        raise RuntimeError("pywhispercpp not installed and GROQ_API_KEY not set")
