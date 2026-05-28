from agent.classifier import EventType
from agent.reasoners.base import BaseReasoner


def route(event_type: EventType, reasoners: dict[EventType, BaseReasoner]) -> BaseReasoner:
    """Return the right reasoner for this event type, falling back to DEFAULT."""
    return reasoners.get(event_type) or reasoners[EventType.DEFAULT]
