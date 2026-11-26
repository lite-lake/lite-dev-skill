"""Run the project's own commands as gates. The tool never invents commands."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from . import gate_log
from .profile import Profile, ProfileError

TAIL_LINES = 40


@dataclass
class StepResult:
    name: str
    command: str
    code: int
    duration: float
    output: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def execute(profile: Profile, level: str, timeout: int = 1800) -> list[StepResult]:
    names = profile.gate.get(level)
    if not names:
        raise ProfileError(f"[gate] has no level '{level}' or it has no steps")

    results: list[StepResult] = []
    for name in names:
        command = profile.commands[name]
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=profile.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            code = process.returncode
            output = (process.stdout or "") + (process.stderr or "")
        except subprocess.TimeoutExpired:
            code = 124
            output = f"timed out after {timeout}s"
        results.append(
            StepResult(
                name=name,
                command=command,
                code=code,
                duration=time.monotonic() - started,
                output=output,
            )
        )
        if code != 0:
            break
    return results


def summary(level: str, results: list[StepResult]) -> str:
    ok = bool(results) and all(result.ok for result in results)
    lines = [f"{'PASS' if ok else 'FAIL'} {level}"]
    for result in results:
        lines.append(
            f"- {result.name} {'PASS' if result.ok else 'FAIL'} ({result.duration:.1f}s)"
        )
    return "\n".join(lines)


def print_results(level: str, results: list[StepResult]) -> int:
    print(f"gate {level}: {', '.join(result.name for result in results)}")
    for result in results:
        print(f"  {'PASS' if result.ok else 'FAIL'} {result.name} ({result.duration:.1f}s)")
        if not result.ok:
            lines = result.output.strip().splitlines()
            for line in lines[-TAIL_LINES:]:
                print(f"    {line}")
            if len(lines) > TAIL_LINES:
                print(f"    ... {len(lines) - TAIL_LINES} more lines")
    ok = bool(results) and all(result.ok for result in results)
    if ok:
        print(f"gate {level}: PASS")
        return 0
    last = results[-1] if results else None
    if last is not None:
        print(f"gate {level}: FAIL at '{last.name}' (exit {last.code})")
    else:
        print(f"gate {level}: FAIL (no steps)")
    return 1


def run_gate(profile: Profile, level: str, timeout: int = 1800, item: str = "") -> int:
    results = execute(profile, level, timeout=timeout)
    code = print_results(level, results)
    gate_log.record(profile, level, code == 0, item=item)
    return code
