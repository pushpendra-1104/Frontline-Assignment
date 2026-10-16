# Offline voice-agent evaluation design

## Scope

This suite is a deterministic contract evaluation for the single-prompt voice
agent. It reuses production prompt construction and tool handlers, while
replacing all side-effecting dependencies with recording fakes. It deliberately
does not start the Pipecat/Daily pipeline or call an LLM.

This distinction matters: a passing result establishes that a proposed action
trace is compatible with the prompt/tool contracts and that production handlers
perform safe expected effects. It does **not** establish that `gpt-4.1` will
choose those actions in a live voice call.

## What is measured

- Identity and load handler ordering/outputs.
- Rejection of malformed references before a repository request.
- Context mutation after load retrieval and prompt replacement.
- Agreement, above-max, quote, and end-call side-effect intents.
- Transfer preconditions, routing, and scheduling intent.
- Deterministic fixture-text checks for confidential-rate leakage.
- An explicit regression characterization of the current prompt-only
  agreement-confirmation guard.

## Implemented scenarios and blocking assertions

| Scenario | Production path exercised | Blocking evidence |
| --- | --- | --- |
| `happy_path_agreement` | `verify_carrier` → `get_load_context` → `record_agreement` → `end_call` | Correct context/prompt mutation, one agreement and quote intent, agreement end frame, no fixture confidentiality leak. |
| `mc_not_found_three_strikes` | `verify_carrier`, `end_call` | Three real lookup callbacks are `not_found`; the fixture closes with `mc_not_found` and never loads a load. Strike counting is explicitly prompt-owned. |
| `invalid_reference_then_valid_reference` | `get_load_context` | Malformed reference cannot reach the repository; a valid one replaces the prompt and establishes load state. |
| `above_max_bid` | `record_agreement`, `end_call` | Above-max record has required contact data, creates no quote intent, and ends `bid_placed`. |
| `ambiguous_acceptance_guard_gap` | `record_agreement` | Characterizes (rather than hides) that backend currently accepts a normal record without acceptance/contact evidence. |
| `transfer_guards_and_schedule` | `TransferToolHandler.handle_transfer_to_human` | Missing load is blocked; a routed load emits transfer metadata and a deferred intent without running Daily. |
| `phone_identity_denial` | production transcript identity helper | A denial clears staged phone-first identity before a replacement lookup. |

Fixture assistant wording is checked only where a deterministic commercial
invariant is available (for example, protected-price leakage). It is not used
as evidence of model adherence.

## Scenario result meanings

- **PASS**: a deterministic handler/trace assertion held.
- **FAIL**: the callback, context mutation, or captured side effect violated a
  required invariant.
- **GUARD GAP (expected characterization)**: the suite demonstrated a known
  behavior that the backend does not prevent. This is evidence, not a passing
  safety guarantee.
- **MODEL_UNVERIFIED**: no model selected assistant text/tool calls.
- **INTEGRATION_UNVERIFIED**: real providers were not exercised.

## Omitted intentionally

Daily rooms/PSTN/SIP transfer, Deepgram transcription, Cartesia audio quality,
OpenAI model adherence, Supabase storage, Highway data quality, KCH quote API,
and Slack delivery need credentialed integration qualification. They are not
safe prerequisites for a merge-time offline suite.
