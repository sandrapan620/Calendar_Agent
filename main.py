import click
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.prompt import Confirm

from gcal.client import list_events, create_tentative_event, find_free_slot
from agent.classifier import classify_all, EventType
from agent.pipeline import PipelineContext
from agent.router import route
from agent.reasoners.exam import ExamReasoner
from agent.reasoners.meeting import MeetingReasoner
from agent.reasoners.default import DefaultReasoner
from output.renderer import render
from output.schema import ReasonerOutput

console = Console()

REASONERS = {
    EventType.EXAM: ExamReasoner(),
    EventType.MEETING: MeetingReasoner(),
    EventType.DEFAULT: DefaultReasoner(),
}

# Keywords in suggested_action that imply a new calendar block should be created
_SCHEDULE_KEYWORDS = {"block", "schedule", "study", "prep", "review", "set aside", "dedicate", "session"}

# How many hours to block based on effort score
_EFFORT_HOURS = {1: 0.5, 2: 1.5, 3: 2.0}


def _is_schedulable(output: ReasonerOutput) -> bool:
    """True if the suggested action implies creating a new calendar block."""
    action_lower = output.suggested_action.lower()
    return output.urgency >= 2 and any(kw in action_lower for kw in _SCHEDULE_KEYWORDS)


def _auto_schedule(outputs: list[ReasonerOutput], events: list) -> None:
    """
    For each schedulable output, find a free slot before the event and propose
    all blocks in a single confirmation prompt.
    """
    schedulable = [o for o in outputs if _is_schedulable(o)]
    if not schedulable:
        return

    # Match each output back to its original event to get the deadline datetime
    event_by_id = {e.id: e for e in events}

    proposals: list[tuple[ReasonerOutput, datetime, datetime]] = []

    # Accumulate slots already proposed this session so later searches don't overlap them
    pending_busy: list[tuple[datetime, datetime]] = []

    console.print("\n[bold]Finding free slots for suggested prep blocks...[/bold]")
    for output in schedulable:
        event = event_by_id.get(output.event_id)
        deadline = event.start if event else datetime.now(timezone.utc) + timedelta(days=1)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        hours = _EFFORT_HOURS.get(output.effort, 1.0)
        slot = find_free_slot(before=deadline, duration_hours=hours, pending_busy=pending_busy)

        if slot:
            slot_end = slot + timedelta(hours=hours)
            proposals.append((output, slot, slot_end))
            # Mark this slot as busy so the next search avoids it
            pending_busy.append((slot, slot_end))
            console.print(
                f"  [dim]{output.event_title}[/dim] → "
                f"{slot.strftime('%a %b %d, %H:%M')}–{slot_end.strftime('%H:%M')} "
                f"({hours}h)"
            )
        else:
            console.print(f"  [yellow]No free slot found before {output.event_title}[/yellow]")

    if not proposals:
        return

    console.print()
    if not Confirm.ask(f"Create {len(proposals)} [TENTATIVE] prep block(s)?", default=False):
        return

    for output, start, end in proposals:
        title = f"{output.event_title} — Prep"
        description = f"Suggested by calendar agent.\n\n{output.reasoning}"
        created = create_tentative_event(title, start, end, description)
        console.print(f"  [green]✓[/green] [TENTATIVE] {title}  {start.strftime('%a %b %d, %H:%M')}–{end.strftime('%H:%M')}")
        link = created.get("htmlLink", "")
        if link:
            console.print(f"    {link}")


@click.group()
def cli():
    pass


@cli.command()
@click.option("--days", default=7, show_default=True, help="How many days ahead to fetch events.")
def batch(days: int):
    """Fetch calendar events and produce recommendations for each."""

    console.print(f"[bold]Fetching events for the next {days} day(s)...[/bold]")
    events = list_events(days_ahead=days)

    if not events:
        console.print("[yellow]No upcoming events found.[/yellow]")
        return

    console.print(f"Found [bold]{len(events)}[/bold] event(s). Classifying...")
    event_types = classify_all(events)

    # Build context once — all reasoners share this same object
    context = PipelineContext(all_events=events)

    outputs = []
    for event, etype in zip(events, event_types):
        console.print(f"  Reasoning about: [dim]{event.title}[/dim] ({etype.value})")
        reasoner = route(etype, REASONERS)
        output = reasoner.run(event, context)
        outputs.append(output)

    console.print()
    render(outputs)
    _auto_schedule(outputs, events)


if __name__ == "__main__":
    cli()
