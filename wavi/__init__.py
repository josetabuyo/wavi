"""wavi — WhatsApp automation via vision."""

from wavi.runner import WARunner, run_enhanced, transcribe_history_audios
from wavi.session import WASession
from wavi.vision import Bubble

__all__ = [
    "WASession",
    "WARunner",
    "run_enhanced",
    "transcribe_history_audios",
    "Bubble",
]
__version__ = "0.2.0"
