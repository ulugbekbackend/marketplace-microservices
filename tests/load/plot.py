"""Chart of the overselling run for the README: requests per second by status over time, and
how the 100 orders ended.

    uv run python tests/load/plot.py [output.png]     (default docs/load-test/oversell.png)
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests" / "load" / "results"
OUTCOME_COLORS = {"PAID": "#12876A", "CANCELLED": "#C63D2F", "REFUSED": "#C27410"}
STATUS_COLORS = {"2xx": "#12876A", "4xx": "#C27410", "5xx": "#C63D2F"}


def requests_per_second() -> dict[str, dict[int, int]]:
    """Status class -> second since start -> requests, from k6's JSON output."""
    buckets: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    start: float | None = None
    for line in (RESULTS / "raw.json").read_text(encoding="utf-8").splitlines():
        point = json.loads(line)
        if point.get("type") != "Point" or point.get("metric") != "http_reqs":
            continue
        moment = datetime.fromisoformat(point["data"]["time"]).timestamp()
        start = moment if start is None else min(start, moment)
        status = str(point["data"]["tags"].get("status", "0"))
        buckets[f"{status[0]}xx"][int(moment)] += 1
    assert start is not None, "no requests in raw.json"
    origin = int(start)
    return {
        cls: {second - origin: count for second, count in seconds.items()}
        for cls, seconds in buckets.items()
    }


def main() -> None:
    output = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "load-test" / "oversell.png"
    )
    report = json.loads((RESULTS / "verify.json").read_text(encoding="utf-8"))
    series = requests_per_second()

    fig, (timeline, outcomes) = plt.subplots(
        1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [2.2, 1]}
    )
    for cls in ("2xx", "4xx", "5xx"):
        points = series.get(cls, {})
        if not points:
            continue
        seconds = sorted(points)
        timeline.plot(
            seconds, [points[s] for s in seconds], label=cls, color=STATUS_COLORS[cls], linewidth=2
        )
    timeline.set_title("Requests per second by status")
    timeline.set_xlabel("seconds since start")
    timeline.set_ylabel("requests / s")
    timeline.legend(frameon=False)
    timeline.grid(alpha=0.25)

    names = [name for name in ("PAID", "CANCELLED", "REFUSED") if report["outcomes"].get(name)]
    counts = [report["outcomes"][name] for name in names]
    bars = outcomes.bar(names, counts, color=[OUTCOME_COLORS[n] for n in names])
    outcomes.bar_label(bars)
    outcomes.set_title(
        f"{report['buyers']} buyers, {report['stock']} units: "
        f"stock {report['variant']['stock']}, reserved {report['variant']['reserved']}"
    )
    outcomes.set_ylabel("orders")
    for side in ("top", "right"):
        timeline.spines[side].set_visible(False)
        outcomes.spines[side].set_visible(False)

    fig.suptitle(
        f"Checkout overselling test: p95 {report['p95_ms']:.0f} ms, "
        f"{report['server_errors']} server errors",
        fontsize=12,
    )
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    print(f"chart written to {output}")


if __name__ == "__main__":
    main()
