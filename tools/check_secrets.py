"""No secrets in the repository, and ``.env.example`` lists what the stack needs.

    python tools/check_secrets.py        (CI lint job; exit code 1 on a problem)

1. No tracked ``.env`` / key files (``*.pem``, ``*.key``, ``*.p12``, ``secrets/``).
2. No private key blocks and no hard-coded values for secret-looking settings
   (``SECRET_KEY = "..."``, ``API_KEY``, ``TOKEN``, ``PASSWORD``) in tracked files.
3. Every ``${VAR}`` the compose file reads from the environment is in ``.env.example``.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_FILES = re.compile(
    r"(^|/)(\.env(\.local|\.production)?|secrets/.*|.*\.(pem|key|p12|pfx))$"
)
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
# NAME = "literal" / NAME: literal for secret-looking names; env lookups are fine.
ASSIGNED_SECRET = re.compile(
    r"""(?ix)\b([A-Z_]*(SECRET_KEY|API_KEY|_TOKEN|PASSWORD|PASSWD|JWT_SECRET|CLIENT_SECRET))\b
        \s*[:=]\s*["']([^"'${}\s]{8,})["']"""
)
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".webp", ".svg", ".ico", ".woff2", ".pdf"}
SKIP_FILES = {"pnpm-lock.yaml", "uv.lock", ".env.example", "tools/check_secrets.py"}
# Throwaway values that only exist inside test suites.
TEST_PATH = re.compile(r"(^|/)(tests?|e2e|__tests__)/|\.test\.tsx?$")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in out.splitlines() if line]


def file_problems(files: list[str], root: Path = ROOT) -> list[str]:
    problems = [f"{name}: secret file is tracked" for name in files if FORBIDDEN_FILES.search(name)]
    for name in files:
        path = root / name
        if name in SKIP_FILES or path.suffix in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PRIVATE_KEY.search(text):
            problems.append(f"{name}: contains a private key block")
        if TEST_PATH.search(name):
            continue
        for match in ASSIGNED_SECRET.finditer(text):
            problems.append(f"{name}: {match.group(1)} has a hard-coded value")
    return problems


def env_example_problems(root: Path = ROOT) -> list[str]:
    example = (root / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=", example))
    compose = (root / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    # ${VAR}, ${VAR:-default}, ${VAR:?msg}; "$${VAR}" is escaped and belongs to the container.
    used = set(re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)", compose))
    return [
        f".env.example: {name} is used by docker-compose.yml" for name in sorted(used - documented)
    ]


def main() -> int:
    files = tracked_files()
    problems = file_problems(files) + env_example_problems()
    for problem in problems:
        print(problem)
    print(f"{len(files)} tracked files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
