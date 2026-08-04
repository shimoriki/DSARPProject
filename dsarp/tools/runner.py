"""Shared subprocess runner for JVM tool execute-mode (Tasks 4-5).

Records command, return code, logs, and status. On any failure or missing binary
it returns status != 'ok' and the caller emits NO evidence (no fabrication).
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class RunResult:
    status: str                       # ok | missing_binary | failed | error
    command: str = ""
    returncode: int = -1
    stdout_tail: str = ""
    stderr_tail: str = ""
    version: str = ""
    log_path: str = ""
    output_dir: str = ""


@dataclass
class ExecuteResult:
    findings: List = field(default_factory=list)   # List[ToolFinding] / events
    run: RunResult = field(default_factory=lambda: RunResult(status="error"))


def _binary_of(command: str) -> str:
    try:
        return shlex.split(command)[0]
    except Exception:
        return command.split()[0] if command else ""


def run_command(command: str, cwd: Path | None = None, log_path: Path | None = None,
                timeout: int = 3600, env_subst: Dict[str, str] | None = None) -> RunResult:
    if not command:
        return RunResult(status="missing_binary", stderr_tail="no command configured")
    if env_subst:
        for k, v in env_subst.items():
            command = command.replace("{" + k + "}", str(v))
    binary = _binary_of(command)
    # allow either an on-PATH binary or an existing file path
    if shutil.which(binary) is None and not Path(binary).exists():
        return RunResult(status="missing_binary", command=command,
                         stderr_tail=f"binary not found: {binary}")
    try:
        proc = subprocess.run(shlex.split(command), cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return RunResult(status="failed", command=command, stderr_tail="timeout")
    except Exception as exc:
        return RunResult(status="error", command=command, stderr_tail=str(exc)[:300])

    out_tail = (proc.stdout or "")[-2000:]
    err_tail = (proc.stderr or "")[-2000:]
    if log_path:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"$ {command}\n\n[stdout]\n{proc.stdout}\n\n[stderr]\n{proc.stderr}",
                            encoding="utf-8")
    status = "ok" if proc.returncode == 0 else "failed"
    return RunResult(status=status, command=command, returncode=proc.returncode,
                     stdout_tail=out_tail, stderr_tail=err_tail,
                     log_path=str(log_path) if log_path else "")
