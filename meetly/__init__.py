"""Compatibility namespace for the repository's top-level packages.

The imported project keeps its implementation packages at the repository
root.  This namespace preserves the documented ``meetly.*`` imports without
duplicating or moving that working architecture.
"""

from __future__ import annotations

import importlib
import sys


for _name in ("audio", "llm", "core"):
    _module = importlib.import_module(_name)
    sys.modules[f"{__name__}.{_name}"] = _module
    for _loaded_name, _loaded_module in list(sys.modules.items()):
        if _loaded_name.startswith(f"{_name}."):
            sys.modules[
                f"{__name__}.{_loaded_name}"
            ] = _loaded_module

from core import Meeting, MeetingState, MeetingStateError

__all__ = [
    "Meeting",
    "MeetingState",
    "MeetingStateError",
]