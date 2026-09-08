from .summarizer import MeetingSummarizer
from .action_items import ActionItemExtractor


def __getattr__(name: str):
    if name == "MeetingQnA":
        from .qna import MeetingQnA

        return MeetingQnA
    raise AttributeError(name)

__all__ = [
    "MeetingSummarizer",
    "ActionItemExtractor",
    "MeetingQnA",
]