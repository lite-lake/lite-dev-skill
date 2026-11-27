"""Run the project's own commands as gates. The tool never invents commands.

A workspace has one command set and several working directories: a command may
name a `dir`, and then it belongs to that repository. The gate runs only the
commands of the repositories the change touches, so `l1` stays cheap without
weakening what it proves.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field

from . import gate_log
from .profile import Profile, ProfileError, is_unconfigured

TAIL_LINES = 40


@dataclass
class StepResult:
    name: str
    command: str
    code: int
    duration: float
    output: str
    repo: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def label(self) -> str:
        return f"{self.name} [{self.repo}]" if self.repo else self.name


@dataclass
class Plan:
    """What a level will run, and what it deliberately skipped."""

    steps: list[str]
    skipped: list[str]
    scope: list[str] | None
    unavailable: list[str] = field(default_factory=list)


def plan(profile: Profile, level: str, repos: list[str] | None = None) -> Plan:
    """Select the steps for a level under a repository scope.

    `repos=None` means "no scoping": every step runs, which is what a single
    repository project has always done. A step with no `dir` is workspace-level
    and always runs. A step whose working directory is missing is reported as
    unavailable, never silently dropped: on some machine a repository is simply
    not checked out, and the gate has to say which one it could not inspect.
    """
    names = profile.gate.get(level)
    if not names:
        raise ProfileError(f"[gate] has no level '{level}' or it has no steps")
    allowed = set(repos) if repos is not None else None
    steps: list[str] = []
    skipped: list[str] = []
    unavailable: list[str] = []
    for name in names:
        if is_unconfigured(profile.commands.get(name, "")):
            raise ProfileError(
                f"gate command '{name}' is not wired; set [commands] {name} "
                "(run flow.py init --plan for a proposal)"
            )
        repo = profile.command_repo(name)
        if repo is not None and allowed is not None and repo not in allowed:
            skipped.append(name)
            continue
        directory = profile.command_dirs.get(name, "")
        if directory and not (profile.root / directory).is_dir():
            unavailable.append(directory)
            continue
        steps.append(name)
    return Plan(
        steps=steps,
        skipped=skipped,
        scope=list(repos) if repos is not None else None,
        unavailable=unavailable,
    )


def execute(
    profile: Profile,
    level: str,
    timeout: int = 1800,
    repos: list[str] | None = None,
) -> tuple[list[StepResult], Plan]:
    chosen = plan(profile, level, repos)
    results: list[StepResult] = []
    for name in chosen.steps:
        command = profile.commands[name]
        directory = profile.command_dirs.get(name, "")
        cwd = profile.root / directory if directory else profile.root
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
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
                repo=directory,
            )
        )
        if code != 0:
            break
    return results, chosen


def summary(level: str, results: list[StepResult]) -> str:
    ok = bool(results) and all(result.ok for result in results)
    lines = [f"{'PASS' if ok else 'FAIL'} {level}"]
    for result in results:
        lines.append(
            f"- {result.label} {'PASS' if result.ok else 'FAIL'} ({result.duration:.1f}s)"
        )
    return "\n".join(lines)


def print_results(
    level: str,
    results: list[StepResult],
    chosen: Plan | None = None,
) -> int:
    if chosen is not None and not chosen.steps:
        scope = ", ".join(chosen.scope or []) or "none"
        if chosen.unavailable:
            print(
                f"gate {level}: nothing runnable — not checked out here: "
                + ", ".join(chosen.unavailable)
                + f" (scope: {scope}); fetch the checkout before treating this "
                "level as evidence"
            )
            return 0
        print(
            f"gate {level}: no command applies (scope: {scope}); "
            "nothing to run, and nothing was skipped silently"
        )
        return 0
    print(f"gate {level}: {', '.join(result.label for result in results)}")
    if chosen is not None and chosen.skipped:
        print(f"  skipped (not in scope): {', '.join(chosen.skipped)}")
    if chosen is not None and chosen.unavailable:
        print(
            "  unavailable (not checked out here): "
            + ", ".join(chosen.unavailable)
            + " — this level did not inspect them"
        )
    for result in results:
        print(f"  {'PASS' if result.ok else 'FAIL'} {result.label} ({result.duration:.1f}s)")
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
        print(f"gate {level}: FAIL at '{last.label}' (exit {last.code})")
    else:
        print(f"gate {level}: FAIL (no steps)")
    return 1


def run_gate(
    profile: Profile,
    level: str,
    timeout: int = 1800,
    item: str = "",
    repos: list[str] | None = None,
) -> int:
    results, chosen = execute(profile, level, timeout=timeout, repos=repos)
    code = print_results(level, results, chosen)
    gate_log.record(
        profile,
        level,
        code == 0,
        item=item,
        repos=sorted({result.repo for result in results if result.repo}),
    )
    return code
