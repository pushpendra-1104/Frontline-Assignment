# Offline evaluation suite

Run from `voice-agent/` after installing the existing application dependencies:

```bash
python -m unittest evals.test_offline_evals -v
python evals/run_evals.py
```

The suite has no production credentials and never makes a network call. It
patches carrier lookup, load data, call persistence, quote submission, and
transfer scheduling, then records their intended effects.

Interpret results as deterministic handler/trace evidence only. A passing run
does not validate the production LLM, telephony, STT, TTS, or live external
services; the runner prints these boundaries explicitly.

See [DESIGN.md](DESIGN.md) for scope, pass/fail meanings, known guard gaps, and
the required future integration qualification.
