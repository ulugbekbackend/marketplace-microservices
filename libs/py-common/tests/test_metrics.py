"""Metrics exposition: plain registry, gunicorn multiprocess files and the worker server."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from py_common import metrics

WORKER = """
import os, sys
os.environ["PROMETHEUS_MULTIPROC_DIR"] = sys.argv[1]
from prometheus_client import Counter
Counter("orders_demo_total", "demo").inc(int(sys.argv[2]))
"""


def test_latest_without_multiprocess_uses_the_process_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(metrics.MULTIPROC_ENV, raising=False)

    assert b"python_info" in metrics.latest()


def test_latest_adds_up_every_worker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Each worker is its own process writing its own file, as under gunicorn.
    for amount in ("2", "3"):
        subprocess.run([sys.executable, "-c", WORKER, str(tmp_path), amount], check=True)
    monkeypatch.setenv(metrics.MULTIPROC_ENV, str(tmp_path))

    assert b"orders_demo_total 5.0" in metrics.latest()


def test_child_exit_marks_the_worker_dead(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dead: list[int] = []
    monkeypatch.setenv(metrics.MULTIPROC_ENV, str(tmp_path))
    monkeypatch.setattr("prometheus_client.multiprocess.mark_process_dead", dead.append)

    metrics.child_exit(object(), SimpleNamespace(pid=4242))

    assert dead == [4242]


def test_serve_on_port_zero_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[int] = []
    monkeypatch.setattr(metrics, "start_http_server", started.append)

    metrics.serve(0)
    metrics.serve(9100)

    assert started == [9100]
