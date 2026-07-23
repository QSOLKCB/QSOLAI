from __future__ import annotations

import unittest
from pathlib import Path

from qsolai.engine import execute_pipeline, load_policy, load_task


ROOT = Path(__file__).resolve().parents[1]


def load_example(name: str, task_name: str = "task.json"):
    base = ROOT / "examples" / name
    return load_task(base / task_name), load_policy(base / "policy.json")


class ExampleTests(unittest.TestCase):
    def test_c99_win32_rejects_browser_candidates(self) -> None:
        test_task, test_policy = load_example("c99_win32_constraint")
        result = execute_pipeline(test_task, test_policy)
        self.assertEqual(result.final_state, "COMMITTED")
        selected = next(item for item in result.candidates if item.identity == result.decision.selected_candidate_sha256)
        self.assertIn("C99", selected.answer)
        browser_results = [verification for candidate, verification in zip(result.candidates, result.verification) if "HTML" in candidate.answer]
        self.assertTrue(browser_results)
        self.assertTrue(all(any(code.startswith("FORBIDDEN_CONSTRAINT") for code in item.hard_rejections) for item in browser_results))

    def test_creative_mutation_changes_identity_and_rejects_repeat(self) -> None:
        task_seven, test_policy = load_example("creative_variation")
        task_eight, _ = load_example("creative_variation", "task-mutation-8.json")
        seven = execute_pipeline(task_seven, test_policy)
        eight = execute_pipeline(task_eight, test_policy)
        self.assertNotEqual(seven.run_id, eight.run_id)
        repeated = [verification for candidate, verification in zip(seven.candidates, seven.verification) if candidate.answer == "A previous refrain."]
        self.assertTrue(all("EXACT_HISTORY_REPETITION" in item.hard_rejections for item in repeated))

    def test_research_evidence_candidate_wins(self) -> None:
        test_task, test_policy = load_example("research_adjudication")
        result = execute_pipeline(test_task, test_policy)
        selected = next(item for item in result.candidates if item.identity == result.decision.selected_candidate_sha256)
        self.assertIn("bounded test result", selected.answer)
        self.assertEqual(result.final_state, "COMMITTED")

    def test_medical_support_requires_human_and_reports_disagreement(self) -> None:
        test_task, test_policy = load_example("medical_support_synthetic")
        result = execute_pipeline(test_task, test_policy)
        self.assertEqual(result.final_state, "HUMAN_REVIEW_REQUIRED")
        self.assertTrue(result.decision.unresolved_disagreements)

    def test_legal_support_requires_human_and_reports_disagreement(self) -> None:
        test_task, test_policy = load_example("legal_support_synthetic")
        result = execute_pipeline(test_task, test_policy)
        self.assertEqual(result.final_state, "HUMAN_REVIEW_REQUIRED")
        self.assertTrue(result.decision.unresolved_disagreements)


if __name__ == "__main__":
    unittest.main()
