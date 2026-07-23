"""Argparse command-line interface for QSOLAI v0.1.0."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .archive import pack_run
from .artifacts import verify_run_directory
from .canonical import canonical_bytes, parse_json_bytes
from .contracts import DEFAULT_RANKING, ROLES, CompiledPlan, DecisionReceipt, RunManifest
from .engine import approve_run, import_observation, load_policy, load_task, replay_run, run_to_directory
from .errors import QSOLAIError
from .planner import compile_plan
from .selftest import run_selftest


SIZE_LIMIT = 1_350_000


class QSOLAIArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise QSOLAIError("CLI_ARGUMENT_INVALID", message)


def _emit(value: object, *, error: bool = False) -> None:
    stream = sys.stderr.buffer if error else sys.stdout.buffer
    stream.write(canonical_bytes(value) + b"\n")


def _template_task() -> dict[str, object]:
    return {
        "schema": "qsolai.task/v1",
        "task_id": "example-task",
        "task_class": "bounded_generation",
        "goal": "Produce one bounded proposal.",
        "risk_tier": "LOW",
        "determinism_mode": "CAPTURED_LIVE",
        "execution_profile": "SIM_ONLY",
        "constraints": [],
        "evidence_requirements": [],
        "forbidden_actions": ["execute external action"],
        "mutation_index": 0,
        "run_nonce": "example-run",
        "history_catalogue": [],
    }


def _template_policy() -> dict[str, object]:
    response = {
        "protocol": "qsolai.worker-result/v1",
        "summary": "Example deterministic mock proposal",
        "claims": [],
        "uncertainties": ["This is a synthetic MockAdapter response."],
        "constraint_report": {"satisfied": [], "possibly_violated": []},
        "proposed_actions": [],
        "answer": "Bounded proposal generated under SIM_ONLY authority.",
    }
    return {
        "schema": "qsolai.policy/v1",
        "policy_id": "example-policy",
        "execution_profile": "SIM_ONLY",
        "support_profile": "NONE",
        "human_approval_required": False,
        "required_independent_backends": 1,
        "max_observation_bytes": 65536,
        "worker_timeout_ms": 2000,
        "capability_grants": [
            {
                "schema": "qsolai.capability-grant/v1",
                "grant_id": "mock-only",
                "execution_profile": "SIM_ONLY",
                "allowed_adapters": ["MOCK"],
                "allow_subprocess": False,
                "argv": [],
                "environment": {},
            }
        ],
        "agents": [
            {
                "schema": "qsolai.agent/v1",
                "agent_id": "example-mock",
                "backend_id": "mock-backend",
                "adapter": "MOCK",
                "roles": list(ROLES),
                "capability_grant_id": "mock-only",
                "mock_response": response,
            }
        ],
        "style": {
            "schema": "qsolai.style/v1",
            "required_phrases": [],
            "forbidden_phrases": [],
            "max_output_bytes": 32768,
            "max_repeated_line_count": 2,
        },
        "forbidden_authority_phrases": [],
        "anti_repetition_enabled": False,
        "maximum_attempts": 16,
        "ranking": list(DEFAULT_RANKING),
    }


def command_init(args: argparse.Namespace) -> dict[str, object]:
    target = Path(args.directory)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise QSOLAIError("INIT_DIRECTORY_NOT_EMPTY", "init directory exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    files = {"task.json": canonical_bytes(_template_task()), "policy.json": canonical_bytes(_template_policy())}
    for name, body in files.items():
        with (target / name).open("xb") as handle:
            handle.write(body)
    return {"status": "PASS", "directory": str(target), "files": sorted(files)}


def command_validate(args: argparse.Namespace) -> dict[str, object]:
    task = load_task(Path(args.task))
    output: dict[str, object] = {"status": "PASS", "task_sha256": task.identity}
    if args.policy:
        policy = load_policy(Path(args.policy))
        compile_plan(task, policy)
        output["policy_sha256"] = policy.identity
    return output


def command_plan(args: argparse.Namespace) -> dict[str, object]:
    task = load_task(Path(args.task))
    policy = load_policy(Path(args.policy))
    plan = compile_plan(task, policy)
    return {"status": "PASS", "plan_sha256": plan.identity, "plan": plan.to_dict()}


def command_run(args: argparse.Namespace) -> dict[str, object]:
    task = load_task(Path(args.task))
    policy = load_policy(Path(args.policy))
    run_dir, result = run_to_directory(task, policy, Path(args.runs_dir), run_name=args.run_name, allow_subprocess=args.allow_subprocess)
    manifest = RunManifest.from_dict(parse_json_bytes((run_dir / "manifest.json").read_bytes()))
    return {"status": "PASS", "run_directory": str(run_dir), "run_id": result.run_id, "final_state": result.final_state, "decision_sha256": result.decision.identity, "manifest_sha256": manifest.manifest_core_sha256}


def command_import(args: argparse.Namespace) -> dict[str, object]:
    return import_observation(Path(args.run), args.slot, Path(args.file))


def command_approve(args: argparse.Namespace) -> dict[str, object]:
    return approve_run(Path(args.run), args.reviewer, args.decision, args.notes)


def command_inspect(args: argparse.Namespace) -> dict[str, object]:
    report = verify_run_directory(Path(args.run))
    decision = DecisionReceipt.from_dict(parse_json_bytes((Path(args.run) / "decision.json").read_bytes()))
    return {**report, "decision_sha256": decision.identity, "selected_candidate_sha256": decision.selected_candidate_sha256, "human_approval_required": decision.human_approval_required, "unresolved_disagreements": list(decision.unresolved_disagreements)}


def command_diff(args: argparse.Namespace) -> dict[str, object]:
    left = RunManifest.from_dict(parse_json_bytes((Path(args.run_a) / "manifest.json").read_bytes()))
    right = RunManifest.from_dict(parse_json_bytes((Path(args.run_b) / "manifest.json").read_bytes()))
    left_rows = {str(item["path"]): str(item["sha256"]) for item in left.artifacts}
    right_rows = {str(item["path"]): str(item["sha256"]) for item in right.artifacts}
    paths = sorted(set(left_rows) | set(right_rows))
    changes = [{"path": path, "left_sha256": left_rows.get(path), "right_sha256": right_rows.get(path)} for path in paths if left_rows.get(path) != right_rows.get(path)]
    return {"status": "PASS", "identical": not changes, "left_manifest_sha256": left.identity, "right_manifest_sha256": right.identity, "changes": changes}


def command_size(args: argparse.Namespace) -> dict[str, object]:
    path = Path(args.artifact)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise QSOLAIError("SIZE_ARTIFACT_MISSING", f"size artifact is missing: {path}") from exc
    if size > SIZE_LIMIT:
        raise QSOLAIError("SIZE_LIMIT_EXCEEDED", f"artifact is {size} bytes; limit is {SIZE_LIMIT}")
    return {"status": "PASS", "path": str(path), "byte_length": size, "limit": SIZE_LIMIT, "remaining": SIZE_LIMIT - size}


def build_parser() -> argparse.ArgumentParser:
    parser = QSOLAIArgumentParser(prog="qsolai", description="Deterministic orchestration kernel for bounded agent systems")
    parser.add_argument("--version", action="version", version="QSOLAI 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=QSOLAIArgumentParser)

    init = commands.add_parser("init")
    init.add_argument("directory", nargs="?", default="qsolai-project")
    init.set_defaults(handler=command_init)

    validate = commands.add_parser("validate")
    validate.add_argument("task")
    validate.add_argument("--policy")
    validate.set_defaults(handler=command_validate)

    plan = commands.add_parser("plan")
    plan.add_argument("task")
    plan.add_argument("--policy", required=True)
    plan.set_defaults(handler=command_plan)

    run = commands.add_parser("run")
    run.add_argument("task")
    run.add_argument("--policy", required=True)
    run.add_argument("--runs-dir", default="runs")
    run.add_argument("--run-name")
    run.add_argument("--allow-subprocess", action="store_true")
    run.set_defaults(handler=command_run)

    imported = commands.add_parser("import-observation")
    imported.add_argument("run")
    imported.add_argument("slot")
    imported.add_argument("file")
    imported.set_defaults(handler=command_import)

    approve = commands.add_parser("approve")
    approve.add_argument("run")
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--decision", choices=("accept", "reject"), required=True)
    approve.add_argument("--notes", default="")
    approve.set_defaults(handler=command_approve)

    verify = commands.add_parser("verify")
    verify.add_argument("run")
    verify.set_defaults(handler=lambda args: verify_run_directory(Path(args.run)))

    replay = commands.add_parser("replay")
    replay.add_argument("run")
    replay.set_defaults(handler=lambda args: replay_run(Path(args.run)))

    inspect = commands.add_parser("inspect")
    inspect.add_argument("run")
    inspect.set_defaults(handler=command_inspect)

    diff = commands.add_parser("diff")
    diff.add_argument("run_a")
    diff.add_argument("run_b")
    diff.set_defaults(handler=command_diff)

    pack = commands.add_parser("pack")
    pack.add_argument("run")
    pack.add_argument("--output")
    pack.set_defaults(handler=lambda args: (verify_run_directory(Path(args.run)), pack_run(Path(args.run), Path(args.output) if args.output else None))[1])

    selftest = commands.add_parser("selftest")
    selftest.set_defaults(handler=lambda _args: run_selftest())

    size = commands.add_parser("size")
    size.add_argument("artifact", nargs="?", default="dist/qsolai.pyz")
    size.set_defaults(handler=command_size)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = args.handler(args)
        _emit(result)
        return 0
    except QSOLAIError as exc:
        _emit({"status": "FAIL", "error_code": exc.code, "message": exc.message}, error=True)
        raise SystemExit(exc.exit_code) from None
    except (OSError, ValueError, TypeError) as exc:
        _emit({"status": "FAIL", "error_code": "UNHANDLED_INPUT_ERROR", "message": str(exc)}, error=True)
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
