"""Every image runs as a non-root user and is built from pinned images.

    python tools/check_dockerfiles.py        (CI lint job; exit code 1 on a problem)

Checks each Dockerfile (every FROM names an exact tag, the final stage switches to a non-root
USER) and the compose file (every image has an exact tag, never ``latest``).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_USERS = {"root", "0", "0:0", "root:root"}
TAG = re.compile(r"^[\w./-]+:(?!latest\b)[\w.-]*\d[\w.-]*(@sha256:[0-9a-f]{64})?$")


def dockerfile_problems(path: Path) -> list[str]:
    problems: list[str] = []
    stages: list[str] = []
    user: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        word, _, rest = line.partition(" ")
        if word.upper() == "FROM":
            image = rest.split()[0]
            stages.append(image)
            user = None  # every stage starts as root
            if image not in stages[:-1] and not TAG.match(image) and not _is_stage(image, path):
                problems.append(f"{path}: FROM {image} is not pinned to an exact version")
        elif word.upper() == "USER":
            user = rest.strip()
    if user is None or user in ROOT_USERS:
        problems.append(f"{path}: the final stage runs as root (no non-root USER)")
    return problems


def _is_stage(name: str, path: Path) -> bool:
    """``FROM builder`` refers to an earlier ``AS builder`` stage."""
    text = path.read_text(encoding="utf-8")
    return re.search(rf"(?im)^FROM\s+\S+\s+AS\s+{re.escape(name)}\s*$", text) is not None


def compose_problems(path: Path) -> list[str]:
    problems: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"\s*image:\s*(\S+)", raw)
        if match and not TAG.match(match.group(1)):
            problems.append(f"{path}:{number}: image {match.group(1)} is not pinned")
    return problems


def main() -> int:
    dockerfiles = sorted(
        p
        for p in ROOT.glob("**/Dockerfile")
        if "node_modules" not in p.parts and ".tools" not in p.parts
    )
    problems = [problem for path in dockerfiles for problem in dockerfile_problems(path)]
    problems += compose_problems(ROOT / "infra" / "docker-compose.yml")
    for problem in problems:
        print(problem)
    print(f"{len(dockerfiles)} Dockerfiles checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
