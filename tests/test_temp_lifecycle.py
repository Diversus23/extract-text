"""Реальные процессы: аварийные остатки и изоляция параллельных воркеров."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

WORKER = """
import asyncio, json, sys, tempfile
from pathlib import Path
from app.main import app, lifespan
async def main():
    async with lifespan(app):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"unfinished operation")
            path = f.name
        Path(sys.argv[1]).write_text(json.dumps(path))
        await asyncio.to_thread(sys.stdin.readline)
asyncio.run(main())
"""


@pytest.fixture
def workers(tmp_path):
    processes = []

    def start():
        ready = tmp_path / f"ready-{len(processes)}.json"
        env = dict(
            os.environ,
            TMPDIR=str(tmp_path),
            TEMP=str(tmp_path),
            TMP=str(tmp_path),
            ENABLE_TRANSCRIPTION="false",
        )
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER, str(ready)],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        processes.append(process)
        deadline = time.monotonic() + 20
        while (
            not ready.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert ready.exists(), "Worker failed to start"
        return process, Path(json.loads(ready.read_text()))

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_restart_removes_crashed_worker_files(workers):
    process, old_file = workers()
    process.kill()
    process.communicate(timeout=10)
    assert old_file.exists()
    _, new_file = workers()
    assert new_file.exists()
    assert not old_file.exists()
    assert not old_file.parent.exists()


def test_live_workers_have_separate_protected_directories(workers):
    _, first = workers()
    _, second = workers()
    assert first.parent != second.parent
    assert first.read_bytes() == second.read_bytes() == b"unfinished operation"


def test_graceful_shutdown_removes_own_directory(workers):
    process, file = workers()
    process.communicate(input=b"stop\n", timeout=15)
    assert process.returncode == 0
    assert not file.parent.exists()


def test_collector_removes_dead_worker_while_other_stays_alive(workers):
    from app.temp_workspace import TempWorkspace

    dead_process, dead_file = workers()
    _, live_file = workers()
    dead_process.kill()
    dead_process.communicate(timeout=10)
    TempWorkspace(root=live_file.parent.parent).collect()
    assert not dead_file.parent.exists()
    assert live_file.read_bytes() == b"unfinished operation"
