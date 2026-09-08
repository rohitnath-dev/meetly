"""Meetly source tree marker.

The public ``meetly`` namespace is provided by the compatibility package in
``meetly/``; the implementation packages remain at the repository root.
"""

from pathlib import Path
import sys

_source_root = str(Path(__file__).resolve().parent)
if _source_root not in sys.path:
    sys.path.insert(0, _source_root)

__all__ = [
    "Meeting",
    "MeetingState",
    "MeetingStateError",
]