#!/usr/bin/env python3
"""Public SDK acceptance; execute only in the new remote task namespace."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import time


def completed(reply: dict) -> None:
    if reply.get("http_status") != 200:
        raise AssertionError(f"checkpoint HTTP status: {reply.get('http_status')}")
    if json.loads(reply["body"]) != {"status": "completed"}:
        raise AssertionError("checkpoint did not commit a completed recovery point")


def same_state(before: dict, after: dict) -> None:
    for key in ("pid", "token", "memory_bytes", "sha256", "fd_content"):
        if before[key] != after[key]:
            raise AssertionError(f"restored state differs: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--runtime", choices=("runsc", "firecracker"), required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--memory-bytes", type=int, default=0)
    parser.add_argument("--parameters", action="store_true")
    parser.add_argument("--node-id")
    args = parser.parse_args()
    if os.environ.get("AKERNEL_VERIFY_TLS", "").lower() not in ("true", "1"):
        raise RuntimeError("AKERNEL_VERIFY_TLS must explicitly enable certificate verification")
    if not os.environ.get("SSL_CERT_FILE"):
        raise RuntimeError("private CA SSL_CERT_FILE is required")
    for package, expected in (("akernel-sdk", "0.2.0rc3"), ("adx-environment", "0.1.0rc2")):
        if importlib.metadata.version(package) != expected:
            raise RuntimeError(f"unexpected {package} version")
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    events = os.fdopen(os.open(output / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w")

    def event(kind: str, **data) -> None:
        record = {"event": kind, "unix_ns": time.time_ns(), **data}
        events.write(json.dumps(record, ensure_ascii=False) + "\n")
        events.flush()
        print(json.dumps(record, ensure_ascii=False), flush=True)

    from akernel_sdk import Sandbox

    sandbox = None
    cleanup_safe = True
    results = []
    try:
        start = time.monotonic_ns()
        sandbox = Sandbox(runtime=args.runtime, cpu=1000, memory=2048, storage_mb=1024,
                          idle_timeout=900, failover=True, node_id=args.node_id)
        identity = sandbox.id
        event("created", sandbox_id=identity, runtime=args.runtime,
              create_ms=(time.monotonic_ns() - start) / 1e6)
        facades = (sandbox.commands, sandbox.files, sandbox.pty)
        sandbox.files.write("/tmp/checkpoint-probe", Path(args.probe).read_bytes())

        def command(text: str, timeout: int = 180):
            result = sandbox.commands.run(text, timeout=timeout)
            if result.exit_code != 0:
                event("command_failed", exit_code=result.exit_code, stderr=result.stderr[-2000:])
                raise RuntimeError("sandbox command failed; inspect private evidence")
            return result.stdout

        command("chmod 700 /tmp/checkpoint-probe")

        def probe(mode: str, body: str | None = None) -> dict:
            text = "/tmp/checkpoint-probe " + mode
            if mode == "checkpoint":
                text += " --socket /run/akernel/execd.sock --timeout 150"
                if body is not None:
                    text += " --body " + shlex.quote(body)
            return json.loads(command(text))

        if args.parameters:
            cases = ["{", '{"timeoutSeconds":0}', '{"timeoutSeconds":-1}',
                     '{"timeoutSeconds":3601}', '{"timeoutSeconds":1.5}',
                     '{"timeoutSeconds":"120"}', '{"unexpected":1}',
                     '{"padding":"' + "x" * 1100 + '"}']
            for index, body in enumerate(cases):
                reply = probe("checkpoint", body)
                if reply["http_status"] not in (400, 413):
                    raise AssertionError(f"invalid parameter accepted or wrong endpoint: {index}")
                event("parameter_rejected", case=index, http_status=reply["http_status"])

        before_memory = None
        if args.memory_bytes:
            sandbox.commands.run("/tmp/checkpoint-probe hold --bytes " + str(args.memory_bytes)
                                 + " >/tmp/checkpoint-probe-hold.log 2>&1", background=True)
            deadline = time.monotonic() + 120
            while True:
                result = sandbox.commands.run("/tmp/checkpoint-probe state", timeout=30)
                if result.exit_code == 0:
                    before_memory = json.loads(json.loads(result.stdout)["body"])
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("memory holder did not become ready")
                time.sleep(0.5)
            if before_memory["memory_bytes"] != args.memory_bytes:
                raise AssertionError("wrong resident-memory probe size")
            event("memory_ready", **before_memory)

        for index in range(args.rounds):
            before = f"checkpoint-before-{index}"
            sandbox.files.write("/tmp/checkpoint-private-state", before)
            cleanup_safe = False
            checkpoint = probe("checkpoint")
            completed(checkpoint)
            cleanup_safe = True
            event("checkpoint_completed", round=index, **checkpoint)
            if not sandbox.is_running():
                raise AssertionError("source stopped after successful checkpoint")
            sandbox.files.write("/tmp/checkpoint-private-state", f"source-after-{index}")
            if before_memory is not None:
                mutated = json.loads(probe("mutate")["body"])
                if mutated["sha256"] == before_memory["sha256"]:
                    raise AssertionError("memory mutation did not occur")
                if mutated["fd_content"] != "open-fd-after":
                    raise AssertionError("open file descriptor mutation did not occur")
            reload_start = time.monotonic_ns()
            if not sandbox.reload():
                raise AssertionError("public SDK reload returned False")
            reload_ms = (time.monotonic_ns() - reload_start) / 1e6
            if sandbox.id != identity or any(current is not old for current, old in
                                             zip((sandbox.commands, sandbox.files, sandbox.pty), facades)):
                raise AssertionError("logical identity or public SDK facade changed")
            deadline = time.monotonic() + 120
            while True:
                try:
                    restored = sandbox.files.read("/tmp/checkpoint-private-state")
                except Exception:
                    restored = None
                if restored == before:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError("private writable filesystem did not roll back")
                time.sleep(0.25)
            verified_ms = (time.monotonic_ns() - reload_start) / 1e6
            memory_verified_ms = None
            if before_memory is not None:
                state = json.loads(probe("state")["body"])
                same_state(before_memory, state)
                memory_verified_ms = (time.monotonic_ns() - reload_start) / 1e6
            record = {"round": index, "checkpoint_until_http_completed_ms": checkpoint["elapsed_ms"],
                      "sdk_reload_ms": reload_ms, "first_verified_file_ms": verified_ms,
                      "full_memory_verified_ms": memory_verified_ms}
            results.append(record)
            event("round_passed", **record)
        event("acceptance_passed", rounds=len(results), memory_bytes=args.memory_bytes,
              parameter_cases=8 if args.parameters else 0)
    except Exception as error:
        event("acceptance_failed", error_type=type(error).__name__, detail=str(error)[:2000],
              preserve_for_reconciliation=not cleanup_safe,
              sandbox_id=None if sandbox is None else sandbox.id)
        raise
    finally:
        if sandbox is not None and cleanup_safe:
            try:
                sandbox.kill()
                event("sandbox_deleted", sandbox_id=sandbox.id)
            except Exception as error:
                event("sandbox_delete_failed", error_type=type(error).__name__)
                raise
        events.close()


if __name__ == "__main__":
    main()
