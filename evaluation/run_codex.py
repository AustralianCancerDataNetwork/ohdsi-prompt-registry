"""Explicit opt-in model evaluation using bundled packs and synthetic fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
import tomllib
from pathlib import Path

from codex_client import CodexClient

MODEL = "gpt-6.1-sol"
BOUNDARY = (
    "This is a synthetic evaluation. For pack access use only gw_m4 MCP registry "
    "tools. You may use the native question tool when permitted by the supplied "
    "request policy and preconfigured host mode. Use no other tools. "
    "Do not inspect files, run shell commands, switch host mode, or delegate. "
    "Do not claim that scripted fixture replies establish real human provenance. "
    "Follow the selected pack; load optional references only when needed. "
)


def command_for(installed: Path, root: Path) -> list[str]:
    """Isolate registry access without modifying the user's client configuration."""
    config_path = Path.home() / ".codex" / "config.toml"
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    command = ["codex", "app-server", "--stdio"]
    for name in config.get("mcp_servers", {}):
        command.extend(["-c", f"mcp_servers.{name}.enabled=false"])
    settings = {
        "model": MODEL,
        "mcp_servers.gw_m4.command": str(root / ".venv/bin/python"),
        "mcp_servers.gw_m4.args": [str(root / "evaluation/serve_registry.py")],
        "mcp_servers.gw_m4.env.PYTHONPATH": (
            f"{installed}:{root.parent.parent / 'groundworkers/src'}"
        ),
        # Only this known, bundled-only, read/validate/render server is trusted.
        "mcp_servers.gw_m4.default_tools_approval_mode": "approve",
    }
    for key, value in settings.items():
        command.extend(["-c", f"{key}={json.dumps(value)}"])
    return command


async def run_case(client: CodexClient, case: dict, destination: Path) -> dict:
    record = {"scenario": case["id"], "fixture": case, "turns": []}
    try:
        thread = await client.thread(MODEL)
        for index, turn in enumerate(case["turns"]):
            prompt = (BOUNDARY if index == 0 else "") + turn["text"]
            result = await client.turn(
                thread, prompt, case.get("mode", "default"), turn.get("native_answer")
            )
            record["turns"].append(result)
            destination.write_text(json.dumps(record, indent=2) + "\n")
            if result["completion"].get("turn", {}).get("status") != "completed":
                record["stop_reason"] = result["completion"].get("turn", {}).get(
                    "error", {"message": "Turn did not complete"}
                )
                break
        record["turns_completed"] = "stop_reason" not in record and len(
            record["turns"]
        ) == len(case["turns"])
    except (TimeoutError, RuntimeError) as error:
        record["turns_completed"] = False
        record["stop_reason"] = f"{type(error).__name__}: {error}"
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record


async def repetition(args: argparse.Namespace, cases: list[dict], number: int) -> None:
    destination = args.output / f"rep-{number}"
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).absolute().parent.parent
    client = CodexClient(command_for(args.installed, root), args.cwd, destination)
    try:
        await client.start()
        (destination / "client.json").write_text(
            json.dumps({"model": MODEL, "initialize": client.initialize}, indent=2)
            + "\n"
        )
        for case in cases:
            result = await run_case(client, case, destination / f"{case['id']}.json")
            print(
                f"rep={number} scenario={case['id']} "
                f"turns_completed={result['turns_completed']}",
                flush=True,
            )
    finally:
        await client.close()


async def exercise(args: argparse.Namespace) -> None:
    cases = json.loads(args.fixtures.read_text())
    if args.scenario:
        cases = [case for case in cases if case["id"] in args.scenario]
    if not cases:
        raise ValueError("No selected scenarios")
    args.cwd.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.workers)

    async def bounded(number: int) -> None:
        async with semaphore:
            await repetition(args, cases, number)

    await asyncio.gather(*(bounded(n) for n in range(1, args.repetitions + 1)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true", required=True)
    parser.add_argument("--installed", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--repetitions", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--workers", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    args.installed = args.installed.absolute()
    asyncio.run(exercise(args))


if __name__ == "__main__":
    main()
