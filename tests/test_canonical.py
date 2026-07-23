from __future__ import annotations

import json
import unittest
from pathlib import Path

from qsolai.canonical import canonical_bytes, canonical_json, domain_hash, parse_json_bytes, sha256_bytes
from qsolai.contracts import Constraint, TaskEnvelope
from qsolai.errors import QSOLAIError
from qsolai.implementation import IMPLEMENTATION_MODULES, build_implementation_identity


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "golden.json").read_text(encoding="utf-8"))


class CanonicalTests(unittest.TestCase):
    def test_known_answers(self) -> None:
        value = {"z": {"n": None, "b": True}, "a": [3, 2, 1]}
        self.assertEqual(canonical_json(value), GOLDEN["canonical_json"])
        self.assertEqual(sha256_bytes(canonical_bytes(value)), GOLDEN["canonical_sha256"])
        self.assertEqual(domain_hash("QSOLAI/GOLDEN/v1", value), GOLDEN["domain_sha256"])

    def test_dictionary_order_independence(self) -> None:
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), canonical_bytes({"a": 1, "b": 2}))

    def test_array_order_preserved(self) -> None:
        self.assertNotEqual(canonical_bytes([1, 2]), canonical_bytes([2, 1]))

    def test_float_rejected(self) -> None:
        with self.assertRaises(QSOLAIError):
            canonical_bytes({"x": 1.0})
        with self.assertRaises(QSOLAIError):
            parse_json_bytes(b'{"x":1.0}')

    def test_integer_outside_safe_range_rejected(self) -> None:
        with self.assertRaises(QSOLAIError):
            canonical_bytes({"x": 2**53})

    def test_bool_int_alias_rejected_by_contract(self) -> None:
        with self.assertRaises(QSOLAIError):
            TaskEnvelope("qsolai.task/v1", "x", "x", "x", "LOW", "CAPTURED_LIVE", "SIM_ONLY", (), (), (), True, "n", ())

    def test_nested_identity_inputs_are_frozen(self) -> None:
        terms = ["C99"]
        constraint = Constraint("qsolai.constraint/v1", "native", "REQUIRED", terms, False)  # type: ignore[arg-type]
        terms.append("mutated")
        self.assertEqual(constraint.terms, ("C99",))

    def test_non_string_key_and_cycle_rejected(self) -> None:
        with self.assertRaises(QSOLAIError):
            canonical_bytes({1: "bad"})
        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaises(QSOLAIError):
            canonical_bytes(cyclic)

    def test_duplicate_json_key_rejected(self) -> None:
        with self.assertRaises(QSOLAIError):
            parse_json_bytes(b'{"x":1,"x":2}')

    def test_domain_separation(self) -> None:
        self.assertNotEqual(domain_hash("A", {"x": 1}), domain_hash("B", {"x": 1}))

    def test_source_bundle_identity(self) -> None:
        first = build_implementation_identity()
        second = build_implementation_identity()
        self.assertEqual(first, second)
        self.assertEqual(first["source_bundle_sha256"], GOLDEN["implementation_source_bundle_sha256"])
        self.assertEqual([item["path"] for item in first["source_files"]], [f"qsolai/{name}" for name in IMPLEMENTATION_MODULES])


if __name__ == "__main__":
    unittest.main()
