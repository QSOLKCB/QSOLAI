from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from qsolai.archive import deterministic_zip_bytes, pack_run
from qsolai.artifacts import safe_run_directory, verify_run_directory
from qsolai.contracts import EvidenceRequirement, HumanApprovalReceipt, TaskEnvelope
from qsolai.canonical import canonical_bytes, parse_json_bytes
from qsolai.contracts import RawObservation
from qsolai.engine import approve_run, execute_pipeline, import_observation, replay_run, run_to_directory
from qsolai.errors import QSOLAIError
from tests.helpers import policy, response, task


ROOT = Path(__file__).resolve().parents[1]


class EngineArtifactTests(unittest.TestCase):
    def test_replay_equality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, original = run_to_directory(task(), policy(), Path(directory), run_name="replay-test")
            before = {path.relative_to(run_dir).as_posix(): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            report = replay_run(run_dir)
            after = {path.relative_to(run_dir).as_posix(): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(before, after)
            self.assertEqual(original.final_state, "COMMITTED")

    def test_deterministic_zip_equality_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, _ = run_to_directory(task(), policy(), Path(directory), run_name="zip-test")
            first = deterministic_zip_bytes(run_dir)
            second = deterministic_zip_bytes(run_dir)
            self.assertEqual(first, second)
            with zipfile.ZipFile(BytesIO(first)) as archive:
                self.assertEqual(archive.comment, b"")
                self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist()))
                self.assertTrue(all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist()))
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            with self.assertRaises(QSOLAIError):
                pack_run(run_dir, run_dir / "unsafe.zip")

    def test_unsafe_output_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(QSOLAIError):
                safe_run_directory(Path(directory), "../escape")

    def test_existing_nonempty_directory_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "occupied"
            target.mkdir()
            (target / "user-file").write_text("preserve", encoding="utf-8")
            with self.assertRaises(QSOLAIError):
                safe_run_directory(Path(directory), "occupied")
            self.assertEqual((target / "user-file").read_text(encoding="utf-8"), "preserve")

    def test_manifest_tamper_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, _ = run_to_directory(task(), policy(), Path(directory), run_name="tamper-test")
            (run_dir / "final.txt").write_bytes(b"tampered\n")
            with self.assertRaises(QSOLAIError):
                verify_run_directory(run_dir)

    def high_stakes_inputs(self):
        requirement = EvidenceRequirement("qsolai.evidence-requirement/v1", "record", "Synthetic evidence", True, ("synthetic-1",), "2026-01-01", None)
        claim = {
            "schema": "qsolai.claim/v1",
            "claim_id": "claim",
            "text": "Synthetic review is required.",
            "polarity": "SUPPORT",
            "evidence_references": [{"schema": "qsolai.evidence-reference/v1", "requirement_id": "record", "record_id": "synthetic-1", "source_date": "2026-01-01", "jurisdiction": None}],
        }
        test_task = task(evidence=(requirement,), risk="HIGH")
        test_policy = policy((response("Synthetic bounded support.", claims=[claim]), response("Synthetic bounded dissent.", claims=[claim])), support_profile="MEDICAL_SUPPORT", human=True, required_backends=2)
        return test_task, test_policy

    def test_human_gate_enforcement_and_approval(self) -> None:
        test_task, test_policy = self.high_stakes_inputs()
        with tempfile.TemporaryDirectory() as directory:
            run_dir, pending = run_to_directory(test_task, test_policy, Path(directory), run_name="human-gate")
            self.assertEqual(pending.final_state, "HUMAN_REVIEW_REQUIRED")
            self.assertFalse((run_dir / "human-approval.json").exists())
            approved = approve_run(run_dir, "Reviewer", "accept")
            self.assertEqual(approved["final_state"], "COMMITTED")
            self.assertTrue((run_dir / "human-approval.json").exists())
            self.assertEqual(replay_run(run_dir)["status"], "PASS")

    def test_invalid_human_approval_lineage_rejected(self) -> None:
        test_task, test_policy = self.high_stakes_inputs()
        bad = HumanApprovalReceipt("qsolai.human-approval/v1", "Reviewer", "accept", "0" * 64, "")
        with self.assertRaises(QSOLAIError):
            execute_pipeline(test_task, test_policy, approval=bad)

    def test_mission_critical_support_profile(self) -> None:
        requirement = EvidenceRequirement("qsolai.evidence-requirement/v1", "mission-record", "Synthetic mission record", True, ("mission-1",), "2026-01-01", "Test-Range")
        claim = {
            "schema": "qsolai.claim/v1",
            "claim_id": "mission-claim",
            "text": "The synthetic mission check is bounded.",
            "polarity": "SUPPORT",
            "evidence_references": [{"schema": "qsolai.evidence-reference/v1", "requirement_id": "mission-record", "record_id": "mission-1", "source_date": "2026-01-01", "jurisdiction": "Test-Range"}],
        }
        test_task = task(evidence=(requirement,), risk="MISSION_CRITICAL")
        test_policy = policy((response("Synthetic mission support.", claims=[claim]), response("Synthetic mission review.", claims=[claim])), support_profile="MISSION_CRITICAL_SUPPORT", human=True, required_backends=2)
        result = execute_pipeline(test_task, test_policy)
        self.assertEqual(result.final_state, "HUMAN_REVIEW_REQUIRED")

    def test_canonical_replay_never_invokes_live_worker(self) -> None:
        with self.assertRaises(QSOLAIError):
            execute_pipeline(task(mode="CANONICAL_REPLAY"), policy())

    def test_manual_import_completes_missing_observations(self) -> None:
        test_task = task()
        test_policy = policy(adapter="MANUAL")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, initial = run_to_directory(test_task, test_policy, root, run_name="manual-import")
            self.assertEqual(initial.final_state, "INCOMPLETE")
            source = root / "worker.json"
            source.write_bytes(canonical_bytes(response("Manually captured answer.")))
            for slot in initial.plan.slots:
                report = import_observation(run_dir, slot.slot_id, source)
            self.assertEqual(report["final_state"], "COMMITTED")
            stored = RawObservation.from_dict(parse_json_bytes((run_dir / "observations" / f"{initial.plan.slots[-1].slot_id}.json").read_bytes()))
            self.assertEqual(stored.response_bytes, source.read_bytes())
            self.assertEqual(replay_run(run_dir)["status"], "PASS")

    def test_default_profile_is_simulation_only(self) -> None:
        result = execute_pipeline(task(), policy((response("Proposal", actions=["simulated action"]),)))
        self.assertEqual(result.task.execution_profile, "SIM_ONLY")
        self.assertTrue(all(item.proposed_actions for item in result.candidates))
        with self.assertRaises(QSOLAIError):
            TaskEnvelope("qsolai.task/v1", "x", "x", "x", "LOW", "CAPTURED_LIVE", "WORKSPACE_WRITE", (), (), (), 0, "x", ())

    def test_final_renderer_does_not_rewrite_winner(self) -> None:
        answer = "Exact winning bytes."
        with tempfile.TemporaryDirectory() as directory:
            run_dir, _ = run_to_directory(task(), policy((response(answer),)), Path(directory), run_name="renderer")
            self.assertEqual((run_dir / "final.txt").read_bytes(), b"Exact winning bytes.\n")

    def test_network_audit_and_no_shell_true(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_network.py")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "qsolai").glob("*.py"))
        self.assertNotIn("shell=True", runtime_text)

    def test_cli_argument_failures_are_machine_readable(self) -> None:
        result = subprocess.run([sys.executable, "-m", "qsolai", "not-a-command"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('"error_code":"CLI_ARGUMENT_INVALID"', result.stderr)


if __name__ == "__main__":
    unittest.main()
