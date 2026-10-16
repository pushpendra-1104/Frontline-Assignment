"""Small harness primitives shared by the offline evaluation scenarios.

This module intentionally does not emulate Daily, Pipecat aggregation, or an
LLM.  Scenarios supply proposed assistant actions and exercise the production
handlers against recording fakes.  That distinction is surfaced in reports as
MODEL_UNVERIFIED rather than hidden behind a fake model.
"""

from __future__ import annotations

import json
import inspect
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID


TEST_CALL_ID = UUID("00000000-0000-0000-0000-000000000101")
TEST_ORG_ID = "00000000-0000-0000-0000-000000000201"
TEST_PHONE = "+15555550100"


@dataclass
class Trace:
    """Inspectable record of a scenario's attempted external effects."""

    name: str
    turns: list[dict] = field(default_factory=list)
    callbacks: list[dict] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)

    def turn(self, caller: str, action: str) -> None:
        self.turns.append({"caller": caller, "action": action})

    async def callback(self, payload: str, **_kwargs) -> None:
        self.callbacks.append(json.loads(payload))

    def effect(self, name: str, **details) -> None:
        self.effects.append({"name": name, **details})


class RecordingTask:
    """Captures the end-of-call frame instead of touching a live pipeline."""

    def __init__(self, trace: Trace):
        self.trace = trace

    async def queue_frames(self, frames) -> None:
        self.trace.effect("queue_frames", frame_types=[type(frame).__name__ for frame in frames])


class RecordingSpeechSync:
    """Records a deferred transfer without awaiting its live coroutine."""

    def __init__(self, trace: Trace):
        self.trace = trace

    async def schedule_after_speech(self, _operation) -> None:
        self.trace.effect("transfer_scheduled")
        # Production passes a coroutine which the real synchronizer executes
        # after its hold message. This fake deliberately never executes it;
        # close it so the test does not leak an unawaited coroutine warning.
        if inspect.iscoroutine(_operation):
            _operation.close()


def make_context(system_prompt: str = "initial prompt") -> SimpleNamespace:
    """Build the minimum context shape required by production handlers."""
    return SimpleNamespace(
        messages=[{"role": "system", "content": system_prompt}],
        call_id=TEST_CALL_ID,
        caller_phone=TEST_PHONE,
        org_id=TEST_ORG_ID,
        call_mode="BOT_ACTIVE",
        caller_mc=None,
        caller_dot_number=None,
        carrier_name=None,
        identity_source=None,
        carrier_identity_confirmed=False,
        awaiting_carrier_identity_confirmation=False,
        transcript_messages=[],
    )


def sample_raw_load(*, load_number: str = "TEST-1001", broker_phone: str | None = "+15551234567") -> dict:
    """Current KCH-style load record accepted by production normalization."""
    return {
        "id": load_number,
        "load_number": load_number,
        "offer_rate": 2000,
        "max_pay_amount": 2800,
        "equipment_type_name": "Dry Van",
        "cargo_summary": "Palletized goods",
        "special_requirements": "Tracker required",
        "ready_to_cover": True,
        "carrier_sales_rep_phone": broker_phone,
        "stops": [
            {"stop_number": 1, "is_pickup": True, "stop_city": "Atlanta", "state_code": "GA", "appointment_start": "2026-06-01 08:00"},
            {"stop_number": 2, "is_dropoff": True, "stop_city": "Chicago", "state_code": "IL", "appointment_start": "2026-06-03 10:00"},
        ],
    }


def assert_no_confidential_price(testcase, text: str, *, target: int, maximum: int) -> None:
    """Deterministic leak check for fixture text, not a claim about model behavior."""
    normalized = text.lower().replace(",", "")
    for amount in (target, maximum):
        testcase.assertNotIn(str(amount), normalized, f"confidential ${amount} leaked: {text!r}")
    for forbidden in ("target rate", "max rate", "maximum rate", "budget", "ceiling"):
        testcase.assertNotIn(forbidden, normalized, f"forbidden pricing language: {text!r}")
