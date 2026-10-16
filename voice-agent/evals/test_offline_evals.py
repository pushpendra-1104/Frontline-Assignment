"""Offline scenario contracts using real production handlers and recording fakes.

These tests deliberately evaluate handler and trace contracts. They do not
invoke an LLM, Daily, speech providers, Supabase, Highway, Slack, or KCH.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from call_helpers import end_call, get_load_context, record_agreement, verify_carrier
from load_context_utils import get_initial_system_prompt
from transfer_tool_handler import TransferToolHandler

from evals.offline import (
    RecordingSpeechSync,
    RecordingTask,
    Trace,
    assert_no_confidential_price,
    make_context,
    sample_raw_load,
)


CARRIER = {"data": {"dbaName": "Acme Trucking", "mcNumber": "123456", "dotNumber": "987654"}}


class OfflineScenarioTests(unittest.IsolatedAsyncioTestCase):
    """Critical commercial paths; each test is a self-contained scenario."""

    async def _load(self, context, trace, raw_load=None, reference="TEST-1001"):
        with (
            patch("call_helpers.NegotiationDBService.get_load_by_reference", return_value=raw_load or sample_raw_load()) as get_load,
            patch("call_helpers.update_call_load", side_effect=lambda call_id, load_id: trace.effect("call_load_updated", call_id=str(call_id), load_id=load_id)),
        ):
            await get_load_context("get_load_context", "load-1", {"load_id": reference}, None, context, trace.callback, caller_phone=context.caller_phone)
        return get_load

    async def test_happy_path_agreement_records_safe_intents(self):
        trace = Trace("happy_path_agreement")
        context = make_context(get_initial_system_prompt("KCH"))
        trace.turn("My MC is 123456", "verify_carrier(123456)")
        with (
            patch("call_helpers.fetch_carrier_by_mc", new=AsyncMock(return_value=CARRIER)),
            patch("call_helpers.update_call_mc", side_effect=lambda *args: trace.effect("call_mc_updated")),
        ):
            await verify_carrier("verify_carrier", "mc-1", {"mc_number": "123456"}, None, context, trace.callback)
        self.assertEqual(trace.callbacks[-1]["status"], "success")
        self.assertEqual(context.carrier_name, "Acme Trucking")

        trace.turn("Reference TEST-1001", "get_load_context(TEST-1001)")
        await self._load(context, trace)
        self.assertEqual(trace.callbacks[-1]["status"], "success")
        self.assertEqual(context.load_uuid, "TEST-1001")
        self.assertIn("CONFIDENTIAL PRICING", context.messages[0]["content"])

        spoken = "Great, twenty-three hundred works. Can you send your best phone number and contact name?"
        # Current KCH normalization maps offer_rate to bookNowRate as well as
        # startRate; use that production value rather than a fictitious target.
        assert_no_confidential_price(self, spoken, target=2000, maximum=2800)
        trace.turn("Deal. This is Pat at +15555550101", "record_agreement(2300)")
        negotiation_id = UUID("00000000-0000-0000-0000-000000000301")
        with (
            patch("call_helpers.save_agreement", return_value=negotiation_id) as save,
            patch("call_helpers.NegotiationDBService.notify_carrier_quote", side_effect=lambda **kwargs: trace.effect("quote_intent", **kwargs)) as quote,
        ):
            await record_agreement("record_agreement", "agreement-1", {"agreed_price": 2300, "carrier_contact_name": "Pat", "carrier_contact_phone": "+15555550101"}, None, context, trace.callback)
        save.assert_called_once()
        quote.assert_called_once()
        self.assertEqual(trace.effects[-1]["agreed_price"], 2300.0)

        task = RecordingTask(trace)
        await end_call("end_call", "end-1", {"reason": "agreement"}, None, context, trace.callback, task=task)
        self.assertEqual(context.end_reason, "agreement")
        self.assertEqual(trace.effects[-1]["frame_types"], ["EndFrame"])

    async def test_three_mc_misses_trace_requires_prompt_owned_close(self):
        trace = Trace("mc_not_found_three_strikes")
        context = make_context()
        with patch("call_helpers.fetch_carrier_by_mc", new=AsyncMock(return_value=None)) as lookup:
            for index, mc in enumerate(("111111", "222222", "333333"), start=1):
                trace.turn(f"Try {mc}", f"verify_carrier({mc})")
                await verify_carrier("verify_carrier", f"mc-{index}", {"mc_number": mc}, None, context, trace.callback)
        self.assertEqual(lookup.await_count, 3)
        self.assertTrue(all(result["status"] == "not_found" for result in trace.callbacks))
        # The handler intentionally does not count strikes: the prompt/model owns this decision.
        self.assertFalse(hasattr(context, "end_reason"))
        await end_call("end_call", "end-3", {"reason": "mc_not_found"}, None, context, trace.callback, task=RecordingTask(trace))
        self.assertEqual(context.end_reason, "mc_not_found")

    async def test_malformed_reference_is_blocked_before_repository(self):
        trace = Trace("invalid_reference_then_valid_reference")
        context = make_context()
        with patch("call_helpers.NegotiationDBService.get_load_by_reference") as get_load:
            await get_load_context("get_load_context", "bad-ref", {"load_id": "Noted down"}, None, context, trace.callback, caller_phone=context.caller_phone)
        self.assertEqual(trace.callbacks[-1]["status"], "error")
        get_load.assert_not_called()
        await self._load(context, trace)
        self.assertEqual(context.load_uuid, "TEST-1001")

    async def test_above_max_bid_never_submits_quote(self):
        trace = Trace("above_max_bid")
        context = make_context()
        await self._load(context, trace)
        with (
            patch("call_helpers.save_agreement", return_value=UUID("00000000-0000-0000-0000-000000000302")) as save,
            patch("call_helpers.NegotiationDBService.notify_carrier_quote") as quote,
        ):
            await record_agreement("record_agreement", "bid-1", {"agreed_price": 3000, "above_max": True, "carrier_contact_name": "Pat", "carrier_contact_phone": "+15555550101"}, None, context, trace.callback)
        save.assert_called_once()
        quote.assert_not_called()
        self.assertEqual(trace.callbacks[-1]["status"], "success")
        await end_call("end_call", "end-bid", {"reason": "bid_placed"}, None, context, trace.callback, task=RecordingTask(trace))
        self.assertEqual(context.end_reason, "bid_placed")

    async def test_record_agreement_gap_is_explicitly_characterized(self):
        """Current handler permits a normal record without contact/acceptance evidence."""
        trace = Trace("ambiguous_acceptance_guard_gap")
        context = make_context()
        await self._load(context, trace)
        with (
            patch("call_helpers.save_agreement", return_value=UUID("00000000-0000-0000-0000-000000000303")),
            patch("call_helpers.NegotiationDBService.notify_carrier_quote"),
        ):
            await record_agreement("record_agreement", "premature", {"agreed_price": 2300}, None, context, trace.callback)
        self.assertEqual(trace.callbacks[-1]["status"], "success")
        # This expected success documents a prompt-only guard, not desired policy.

    async def test_transfer_preconditions_and_safe_schedule(self):
        trace = Trace("transfer_guards_and_schedule")
        orchestrator = MagicMock()
        sync = RecordingSpeechSync(trace)
        handler = TransferToolHandler(orchestrator, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), sync, MagicMock(), MagicMock())
        callback = trace.callback

        await handler.handle_transfer_to_human("transfer_to_human", "none", {"reason": "asked", "load_number": "TEST-1001"}, None, SimpleNamespace(), callback)
        self.assertEqual(trace.callbacks[-1]["status"], "error")
        orchestrator.set_transfer_metadata.assert_not_called()

        context = make_context()
        context.load_uuid = "TEST-1001"
        with patch("transfer_tool_handler.NegotiationDBService.get_load", return_value=sample_raw_load()):
            await handler.handle_transfer_to_human("transfer_to_human", "ok", {"reason": "carrier explicitly asked", "load_number": "TEST-1001", "price_asked_by_carrier": 2500}, None, context, callback)
        self.assertEqual(trace.callbacks[-1]["status"], "transferring")
        self.assertEqual(trace.effects[-1]["name"], "transfer_scheduled")
        self.assertEqual(orchestrator.set_transfer_metadata.call_args.kwargs["human_phone_number"], "+15551234567")

    async def test_phone_identity_confirmation_helper_is_exercised(self):
        """The production transcript helper is required for phone-first fidelity."""
        from bot import _handle_carrier_identity_confirmation_from_transcript

        trace = Trace("phone_identity_denial")
        context = make_context()
        context.awaiting_carrier_identity_confirmation = True
        context.caller_mc = "123456"
        context.carrier_name = "Acme Trucking"
        context.identity_source = "highway"
        _handle_carrier_identity_confirmation_from_transcript(context, "No, that is not us")
        self.assertIsNone(context.caller_mc)
        self.assertFalse(context.awaiting_carrier_identity_confirmation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
