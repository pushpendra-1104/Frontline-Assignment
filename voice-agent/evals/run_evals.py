"""Run offline evaluation scenarios without contacting production services."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    # ``python evals/run_evals.py`` places evals/ rather than voice-agent/ on
    # sys.path; add the service root so the evals package and production
    # modules resolve the same way they do under unittest discovery.
    service_root = str(Path(__file__).resolve().parents[1])
    if service_root not in sys.path:
        sys.path.insert(0, service_root)
    suite = unittest.defaultTestLoader.loadTestsFromName("evals.test_offline_evals")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("\nEvaluation scope: deterministic handler/trace contracts only")
    print("MODEL_UNVERIFIED: no LLM was invoked")
    print("VOICE_TELEPHONY_UNVERIFIED: Daily, Deepgram, Cartesia, and audio were not invoked")
    print("LIVE_EXTERNALS_UNVERIFIED: Supabase, Highway, KCH, Slack, and transfers were mocked")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
