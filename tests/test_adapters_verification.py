from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from qsolai.adapters import ManualAdapter, MockAdapter, SubprocessJsonlAdapter, normalize_observation
from qsolai.canonical import canonical_bytes
from qsolai.contracts import Constraint, EvidenceRequirement, EvidenceReference, Claim, Candidate, RawObservation, StyleContract
from qsolai.engine import execute_pipeline
from qsolai.planner import compile_plan
from qsolai.prompting import compile_prompts
from qsolai.verification import normalized_answer_hash, verify_candidate
from tests.helpers import policy, response, task


def first_slot_prompt(test_task, test_policy):
    plan = compile_plan(test_task, test_policy)
    prompt = compile_prompts(test_task, test_policy, plan)[0]
    slot = plan.slots[0]
    agent = next(item for item in test_policy.agents if item.agent_id == slot.agent_id)
    return slot, prompt, agent


class AdapterVerificationTests(unittest.TestCase):
    def test_raw_output_preservation(self) -> None:
        payload = response("Preserve these bytes exactly.")
        test_task = task()
        test_policy = policy((payload,))
        slot, prompt, agent = first_slot_prompt(test_task, test_policy)
        observation = MockAdapter().invoke(task=test_task, policy=test_policy, agent=agent, slot=slot, prompt=prompt)
        self.assertEqual(observation.response_bytes, canonical_bytes(payload))

    def test_invalid_worker_json(self) -> None:
        test_task = task()
        test_policy = policy()
        slot, prompt, agent = first_slot_prompt(test_task, test_policy)
        observation = ManualAdapter({slot.slot_id: b"not-json"}).invoke(task=test_task, policy=test_policy, agent=agent, slot=slot, prompt=prompt)
        self.assertEqual(observation.status, "INVALID_OUTPUT")
        candidate = normalize_observation(observation, slot)
        self.assertTrue(candidate.normalization_errors)

    def test_subprocess_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "slow.py"
            script.write_text("import time\ntime.sleep(1)\n", encoding="utf-8")
            test_task = task()
            test_policy = policy(adapter="SUBPROCESS_JSONL", argv=(sys.executable, str(script)), timeout_ms=10)
            slot, prompt, agent = first_slot_prompt(test_task, test_policy)
            observation = SubprocessJsonlAdapter(cli_granted=True).invoke(task=test_task, policy=test_policy, agent=agent, slot=slot, prompt=prompt)
            self.assertEqual(observation.status, "TIMEOUT")

    def test_subprocess_output_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "large.py"
            script.write_text("import sys\nsys.stdin.buffer.read()\nsys.stdout.write('x' * 4096)\n", encoding="utf-8")
            test_task = task()
            test_policy = policy(adapter="SUBPROCESS_JSONL", argv=(sys.executable, str(script)), max_bytes=128)
            slot, prompt, agent = first_slot_prompt(test_task, test_policy)
            observation = SubprocessJsonlAdapter(cli_granted=True).invoke(task=test_task, policy=test_policy, agent=agent, slot=slot, prompt=prompt)
            self.assertEqual(observation.status, "OUTPUT_LIMIT")
            self.assertEqual(len(observation.response_bytes), 128)

    def test_subprocess_requires_explicit_cli_grant(self) -> None:
        test_task = task()
        test_policy = policy(adapter="SUBPROCESS_JSONL", argv=(sys.executable, "worker.py"))
        slot, prompt, agent = first_slot_prompt(test_task, test_policy)
        observation = SubprocessJsonlAdapter(cli_granted=False).invoke(task=test_task, policy=test_policy, agent=agent, slot=slot, prompt=prompt)
        self.assertEqual(observation.error_code, "SUBPROCESS_NOT_GRANTED")

    def test_exact_constraint_rejection(self) -> None:
        constraint = Constraint("qsolai.constraint/v1", "native", "REQUIRED", ("C99", "Win32"), False)
        test_task = task(constraints=(constraint,))
        result = execute_pipeline(test_task, policy((response("Use HTML and JavaScript."),)))
        self.assertEqual(result.final_state, "REJECTED")
        self.assertTrue(any("REQUIRED_CONSTRAINT:native" in item.hard_rejections for item in result.verification))

    def test_evidence_reference_validation(self) -> None:
        requirement = EvidenceRequirement("qsolai.evidence-requirement/v1", "r", "Synthetic source", True, ("record-1",), "2026-01-01", None)
        claim = {
            "schema": "qsolai.claim/v1",
            "claim_id": "c",
            "text": "Synthetic claim",
            "polarity": "SUPPORT",
            "evidence_references": [{"schema": "qsolai.evidence-reference/v1", "requirement_id": "r", "record_id": "record-2", "source_date": "2026-01-01", "jurisdiction": None}],
        }
        result = execute_pipeline(task(evidence=(requirement,)), policy((response("Synthetic answer", claims=[claim]),)))
        self.assertEqual(result.final_state, "REJECTED")
        self.assertTrue(any("REQUIRED_EVIDENCE_MISSING:r" in item.hard_rejections for item in result.verification))

    def test_unsupported_authority_claim(self) -> None:
        result = execute_pipeline(task(), policy((response("This result is universally binding."),), forbidden_authority=("universally binding",)))
        self.assertEqual(result.final_state, "REJECTED")
        self.assertTrue(any("FORBIDDEN_AUTHORITY_LANGUAGE" in item.hard_rejections for item in result.verification))

    def test_proposed_actions_are_captured_not_executed(self) -> None:
        result = execute_pipeline(task(), policy((response("Bounded answer.", actions=["Draft a simulated file operation."]),)))
        self.assertEqual(result.final_state, "COMMITTED")
        self.assertTrue(all("PROPOSED_ACTIONS_CAPTURED_SIMULATION_ONLY" in item.warnings for item in result.verification))

    def test_style_contract_metrics(self) -> None:
        style = StyleContract("qsolai.style/v1", ("required phrase",), ("forbidden phrase",), 4096, 1)
        result = execute_pipeline(task(), policy((response("forbidden phrase\nforbidden phrase"),), style=style))
        self.assertTrue(all(item.metrics["style_violation_count"] >= 2 for item in result.verification))

    def test_anti_repetition_catalogue(self) -> None:
        answer = "Previously used answer."
        history = (normalized_answer_hash(answer),)
        result = execute_pipeline(task(history=history), policy((response(answer),), anti_repetition=True))
        self.assertEqual(result.final_state, "REJECTED")
        self.assertTrue(any("EXACT_HISTORY_REPETITION" in item.hard_rejections for item in result.verification))

    def test_deterministic_ranking_and_hash_tie_break(self) -> None:
        payload = response("Equal candidate content.")
        result = execute_pipeline(task(), policy((payload, payload)))
        eligible = [candidate.identity for candidate, verification in zip(result.candidates, result.verification) if verification.passed]
        self.assertEqual(result.decision.selected_candidate_sha256, min(eligible))

    def test_completion_order_independence(self) -> None:
        live = execute_pipeline(task(), policy((response("A"), response("B"))))
        reversed_map = dict(reversed([(item.slot_id, item) for item in live.observations]))
        replayed = execute_pipeline(live.task, live.policy, captured=reversed_map)
        self.assertEqual(live.decision.to_canonical_bytes(), replayed.decision.to_canonical_bytes())
        self.assertEqual([item.identity for item in live.candidates], [item.identity for item in replayed.candidates])

    def test_contradictory_and_duplicate_claims(self) -> None:
        reference = EvidenceReference("qsolai.evidence-reference/v1", "r", "record", None, None)
        claims = (
            Claim("qsolai.claim/v1", "a", "Same statement", "SUPPORT", (reference,)),
            Claim("qsolai.claim/v1", "b", "Same statement", "SUPPORT", (reference,)),
            Claim("qsolai.claim/v1", "c", "Same statement", "DENY", (reference,)),
        )
        candidate = Candidate("qsolai.candidate/v1", "slot", "GENERATOR", "backend", "0" * 64, "", claims, (), (), (), (), "Answer", ())
        requirement = EvidenceRequirement("qsolai.evidence-requirement/v1", "r", "Source", True, ("record",), None, None)
        verified = verify_candidate(candidate, task(evidence=(requirement,)), policy())
        self.assertEqual(verified.metrics["duplicate_claim_count"], 1)
        self.assertEqual(verified.metrics["contradiction_count"], 1)


if __name__ == "__main__":
    unittest.main()
