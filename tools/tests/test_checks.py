"""The repository checks catch what they claim to catch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_dockerfiles
import check_secrets

GOOD = """FROM python:3.12.14-slim-bookworm AS builder
RUN echo build
FROM python:3.12.14-slim-bookworm
COPY --from=builder /opt /opt
USER app
"""


def write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_pinned_non_root_dockerfile_passes(tmp_path: Path) -> None:
    assert check_dockerfiles.dockerfile_problems(write(tmp_path, "Dockerfile", GOOD)) == []


def test_unpinned_images_are_reported(tmp_path: Path) -> None:
    text = GOOD.replace("python:3.12.14-slim-bookworm\nCOPY", "python:latest\nCOPY")
    problems = check_dockerfiles.dockerfile_problems(write(tmp_path, "Dockerfile", text))
    assert any("python:latest" in p for p in problems)
    untagged = check_dockerfiles.dockerfile_problems(
        write(tmp_path, "Dockerfile", "FROM node\nUSER node\n")
    )
    assert any("FROM node" in p for p in untagged)


def test_running_as_root_is_reported(tmp_path: Path) -> None:
    for text in (GOOD.replace("USER app\n", ""), GOOD.replace("USER app", "USER root")):
        problems = check_dockerfiles.dockerfile_problems(write(tmp_path, "Dockerfile", text))
        assert any("runs as root" in p for p in problems)


def test_compose_images_must_be_pinned(tmp_path: Path) -> None:
    compose = write(
        tmp_path,
        "docker-compose.yml",
        "services:\n"
        "  a:\n    image: redis:7.4.11-alpine\n"
        "  b:\n    image: grafana/grafana:latest\n",
    )
    problems = check_dockerfiles.compose_problems(compose)
    assert len(problems) == 1 and "grafana/grafana:latest" in problems[0]


def test_secret_files_and_values_are_reported(tmp_path: Path) -> None:
    write(tmp_path, "app/settings.py", 'SECRET_KEY = "a-real-looking-secret-value"\nX = 1\n')
    write(tmp_path, "app/ok.py", 'SECRET_KEY = config("SECRET_KEY")\nTOKEN = ""\n')
    # Built from parts so this file does not trip the pre-commit private key hook itself.
    header = "-----BEGIN RSA " + "PRIVATE KEY-----"
    write(tmp_path, "app/key.txt", f"{header}\nabc\n")
    write(tmp_path, "app/tests/test_x.py", 'PAYME_TOKEN = "throwaway-test-value"\n')
    files = ["app/settings.py", "app/ok.py", "app/key.txt", "app/tests/test_x.py", ".env", "k.pem"]

    problems = check_secrets.file_problems(files, tmp_path)

    assert sorted(problems) == sorted(
        [
            ".env: secret file is tracked",
            "k.pem: secret file is tracked",
            "app/settings.py: SECRET_KEY has a hard-coded value",
            "app/key.txt: contains a private key block",
        ]
    )


def test_env_example_must_cover_compose_variables(tmp_path: Path) -> None:
    write(tmp_path, ".env.example", "DB_PASSWORD=change-me\n")
    write(
        tmp_path,
        "infra/docker-compose.yml",
        'x: ${DB_PASSWORD}\ny: ${GRAFANA_ADMIN_PASSWORD}\nz: "$${CONTAINER_ONLY}"\n',
    )

    assert check_secrets.env_example_problems(tmp_path) == [
        ".env.example: GRAFANA_ADMIN_PASSWORD is used by docker-compose.yml"
    ]
