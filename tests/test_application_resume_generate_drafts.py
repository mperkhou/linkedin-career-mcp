from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_generate_drafts_script() -> ModuleType:
    module_name = "application_resume_generate_drafts_for_tests"
    module_path = PROJECT_ROOT / "scripts" / "application_resume_generate_drafts.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


drafts = _load_generate_drafts_script()


def test_first_draft_llm_timeout_defaults_to_300_seconds() -> None:
    args = drafts.build_arg_parser().parse_args([])

    assert args.llm_timeout_seconds == 300.0
    assert args.llm_retries == 1


@pytest.mark.asyncio
async def test_first_draft_llm_step_times_out_with_job_and_step(capsys) -> None:
    async def slow_operation() -> dict[str, bool]:
        await asyncio.sleep(1)
        return {"ok": True}

    with pytest.raises(TimeoutError) as exc_info:
        await drafts._run_llm_step(
            job_id="url-123",
            step_name="core skill matching",
            timeout_seconds=0.01,
            operation=slow_operation,
        )

    message = str(exc_info.value)
    stderr = capsys.readouterr().err
    assert "core skill matching timed out for url-123 after 0.01 seconds." in message
    assert "[url-123] core skill matching: started (timeout=0.01s)" in stderr
    assert "[url-123] core skill matching: timed out after" in stderr
    assert "core skill matching timed out for url-123 after 0.01 seconds." in stderr


@pytest.mark.asyncio
async def test_first_draft_llm_step_logs_elapsed_completion(capsys) -> None:
    async def fast_operation() -> dict[str, bool]:
        return {"ok": True}

    result = await drafts._run_llm_step(
        job_id="url-123",
        step_name="JOD target extraction",
        timeout_seconds=300,
        operation=fast_operation,
    )

    stderr = capsys.readouterr().err
    assert result == {"ok": True}
    assert "[url-123] JOD target extraction: started (timeout=300s)" in stderr
    assert re.search(
        r"\[url-123\] JOD target extraction: completed in \d+\.\ds",
        stderr,
    )


@pytest.mark.asyncio
async def test_first_draft_llm_step_retries_timeout_once(capsys) -> None:
    calls = 0

    async def flaky_operation() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(1)
        return {"ok": True}

    result = await drafts._run_llm_step(
        job_id="url-123",
        step_name="Oracle experience rewrite",
        timeout_seconds=0.01,
        retry_count=1,
        operation=flaky_operation,
    )

    stderr = capsys.readouterr().err
    assert result == {"ok": True}
    assert calls == 2
    assert "Oracle experience rewrite attempt 1/2: timed out" in stderr
    assert "Oracle experience rewrite: retrying after timeout (attempt 2/2)" in stderr
    assert "Oracle experience rewrite attempt 2/2: completed" in stderr
