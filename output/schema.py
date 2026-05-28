from dataclasses import dataclass, field
from agent.classifier import EventType


@dataclass
class ReasonerOutput:
    event_id: str
    event_title: str
    event_type: EventType
    urgency: int          # 1–3, produced by the LLM
    effort: int           # 1–3, produced by the LLM
    confidence: float     # 0.0–1.0, produced by the LLM
    reasoning: str        # LLM's explanation of its scores
    recommendation: str   # human-readable string from score_rubric(urgency, effort)
    suggested_action: str # e.g. "Block 2h prep on Monday"
    caveats: list[str] = field(default_factory=list)
