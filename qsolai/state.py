"""Forward-only state machine and tamper-evident event chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .canonical import DOMAINS, domain_hash, freeze, without_self_hash
from .contracts import EventRecord
from .errors import QSOLAIError


FORWARD_STATES = (
    "CREATED",
    "VALIDATED",
    "PLANNED",
    "DISPATCH_READY",
    "OBSERVATIONS_CAPTURED",
    "CANDIDATES_NORMALIZED",
    "VERIFIED",
    "ADJUDICATED",
    "HUMAN_REVIEW_REQUIRED",
    "COMMITTED",
)
FAILURE_STATES = {"REJECTED", "ABORTED", "INCOMPLETE", "INVALID"}
ALL_STATES = set(FORWARD_STATES) | FAILURE_STATES
ZERO_HASH = "0" * 64


def _allowed_transition(current: str | None, target: str) -> bool:
    if target not in ALL_STATES:
        return False
    if current is None:
        return target == "CREATED"
    if current in FAILURE_STATES or current == "COMMITTED":
        return False
    if target in FAILURE_STATES:
        return True
    if current == "ADJUDICATED":
        return target in {"HUMAN_REVIEW_REQUIRED", "COMMITTED"}
    if current == "HUMAN_REVIEW_REQUIRED":
        return target == "COMMITTED"
    try:
        return FORWARD_STATES.index(target) == FORWARD_STATES.index(current) + 1
    except ValueError:
        return False


def make_event(sequence: int, event_type: str, previous_hash: str, payload: Mapping[str, Any]) -> EventRecord:
    plain = dict(payload)
    payload_hash = domain_hash("QSOLAI/EVENT-PAYLOAD/v1", plain)
    core = {
        "schema": "qsolai.event/v1",
        "sequence": sequence,
        "event_type": event_type,
        "previous_event_hash": previous_hash,
        "payload_hash": payload_hash,
        "payload": plain,
        "event_hash": "",
    }
    event_hash = domain_hash(DOMAINS["event"], without_self_hash(core, "event_hash"))
    core["event_hash"] = event_hash
    return EventRecord(**core)


@dataclass
class RunStateMachine:
    state: str | None = None
    events: list[EventRecord] = field(default_factory=list)

    def transition(self, target: str, details: Mapping[str, Any] | None = None) -> EventRecord:
        if not _allowed_transition(self.state, target):
            raise QSOLAIError("STATE_TRANSITION_INVALID", f"invalid transition {self.state!r} -> {target!r}")
        payload = {
            "from_state": self.state,
            "to_state": target,
            "details": dict(details or {}),
        }
        previous = self.events[-1].event_hash if self.events else ZERO_HASH
        event = make_event(len(self.events), "STATE_TRANSITION", previous, payload)
        self.events.append(event)
        self.state = target
        return event


def verify_event_chain(events: tuple[EventRecord, ...] | list[EventRecord]) -> str:
    if not events:
        raise QSOLAIError("EVENT_CHAIN_EMPTY", "event chain is empty")
    previous = ZERO_HASH
    state: str | None = None
    seen: set[str] = set()
    for index, event in enumerate(events):
        if type(event) is not EventRecord:
            raise QSOLAIError("EVENT_CHAIN_TYPE", "event chain contains a non-event")
        EventRecord.from_dict(event.to_dict())
        if event.sequence != index:
            raise QSOLAIError("EVENT_CHAIN_SEQUENCE", "event sequence is missing, duplicated or reordered")
        if event.event_hash in seen:
            raise QSOLAIError("EVENT_CHAIN_DUPLICATE", "event hash is duplicated")
        if event.previous_event_hash != previous:
            raise QSOLAIError("EVENT_CHAIN_PREVIOUS", "event previous hash does not match")
        if event.event_type != "STATE_TRANSITION":
            raise QSOLAIError("EVENT_CHAIN_TYPE", "unknown event type")
        payload = event.payload
        if payload.get("from_state") != state:
            raise QSOLAIError("EVENT_CHAIN_STATE", "event from_state does not match prior state")
        target = payload.get("to_state")
        if type(target) is not str or not _allowed_transition(state, target):
            raise QSOLAIError("EVENT_CHAIN_STATE", "event contains an invalid state transition")
        state = target
        previous = event.event_hash
        seen.add(event.event_hash)
    if state is None:
        raise QSOLAIError("EVENT_CHAIN_EMPTY", "event chain did not establish state")
    return state
