from __future__ import annotations

import unittest

from qsolai.contracts import EventRecord
from qsolai.errors import QSOLAIError
from qsolai.planner import compile_plan
from qsolai.state import RunStateMachine, verify_event_chain
from tests.helpers import policy, task


class StatePlannerTests(unittest.TestCase):
    def complete_chain(self) -> RunStateMachine:
        machine = RunStateMachine()
        for state in ("CREATED", "VALIDATED", "PLANNED", "DISPATCH_READY", "OBSERVATIONS_CAPTURED", "CANDIDATES_NORMALIZED", "VERIFIED", "ADJUDICATED", "COMMITTED"):
            machine.transition(state)
        return machine

    def test_state_transition_validity(self) -> None:
        machine = self.complete_chain()
        self.assertEqual(verify_event_chain(machine.events), "COMMITTED")
        with self.assertRaises(QSOLAIError):
            machine.transition("REJECTED")

    def test_invalid_transition_rejected(self) -> None:
        machine = RunStateMachine()
        machine.transition("CREATED")
        with self.assertRaises(QSOLAIError):
            machine.transition("PLANNED")

    def test_event_tamper_detected(self) -> None:
        events = self.complete_chain().events
        data = events[2].to_dict()
        data["payload"]["to_state"] = "INVALID"
        with self.assertRaises(QSOLAIError):
            EventRecord.from_dict(data)

    def test_duplicate_event_rejected(self) -> None:
        events = self.complete_chain().events
        duplicate = list(events)
        duplicate.insert(2, events[1])
        with self.assertRaises(QSOLAIError):
            verify_event_chain(duplicate)

    def test_missing_or_reordered_event_rejected(self) -> None:
        events = self.complete_chain().events
        with self.assertRaises(QSOLAIError):
            verify_event_chain(events[:2] + events[3:])
        reordered = list(events)
        reordered[1], reordered[2] = reordered[2], reordered[1]
        with self.assertRaises(QSOLAIError):
            verify_event_chain(reordered)

    def test_planner_determinism(self) -> None:
        first = compile_plan(task(), policy())
        second = compile_plan(task(), policy())
        self.assertEqual(first.to_canonical_bytes(), second.to_canonical_bytes())

    def test_mutation_index_changes_plan_identity(self) -> None:
        self.assertNotEqual(compile_plan(task(mutation_index=1), policy()).identity, compile_plan(task(mutation_index=2), policy()).identity)


if __name__ == "__main__":
    unittest.main()
