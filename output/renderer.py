from rich.console import Console
from rich.table import Table
from rich import box

from output.schema import ReasonerOutput

console = Console()


def _urgency_color(u: int) -> str:
    return {1: "green", 2: "yellow", 3: "red"}[u]


def _confidence_str(c: float) -> str:
    # Show confidence as a percentage with a colour hint
    pct = int(c * 100)
    color = "green" if pct >= 70 else "yellow" if pct >= 40 else "red"
    return f"[{color}]{pct}%[/{color}]"


def render(outputs: list[ReasonerOutput]) -> None:
    if not outputs:
        console.print("[yellow]No events found in this window.[/yellow]")
        return

    table = Table(
        box=box.ROUNDED,
        show_lines=True,
        title="[bold]Calendar Recommendations[/bold]",
        title_justify="left",
    )

    table.add_column("Event", style="bold", max_width=28, no_wrap=False)
    table.add_column("Type", justify="center", max_width=8)
    table.add_column("U", justify="center", max_width=3)  # Urgency
    table.add_column("E", justify="center", max_width=3)  # Effort
    table.add_column("Conf", justify="center", max_width=6)
    table.add_column("Recommendation", max_width=38, no_wrap=False)
    table.add_column("Suggested Action", max_width=36, no_wrap=False)

    for o in outputs:
        u_color = _urgency_color(o.urgency)
        table.add_row(
            o.event_title,
            o.event_type.value,
            f"[{u_color}]{o.urgency}[/{u_color}]",
            str(o.effort),
            _confidence_str(o.confidence),
            o.recommendation,
            o.suggested_action,
        )

    console.print(table)

    # Print full reasoning underneath the table for any high-urgency events
    high_urgency = [o for o in outputs if o.urgency == 3]
    if high_urgency:
        console.print("\n[bold]Reasoning for high-urgency events:[/bold]")
        for o in high_urgency:
            console.print(f"\n[bold red]{o.event_title}[/bold red]")
            console.print(f"  {o.reasoning}")
            if o.caveats:
                for c in o.caveats:
                    console.print(f"  [yellow]⚠ {c}[/yellow]")
