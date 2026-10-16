# Evaluation run evidence

Run attempted on 2026-10-16 from `voice-agent/`:

```bash
python3 evals/run_evals.py
```

The repository dependency installation could not start in the supplied host:

```text
python3 -m ensurepip --upgrade
/usr/bin/python3: No module named ensurepip

apt-get update && apt-get install -y python3-pip
E: List directory /var/lib/apt/lists/partial is missing. - Acquire (13: Permission denied)
```

Both supported evaluation entry points were then run:

```bash
python3 -m unittest evals.test_offline_evals -v
python3 evals/run_evals.py
```

Both exited with status `1` before loading a scenario. Their common result:

```text
ModuleNotFoundError: No module named 'loguru'
```

The host has Python 3.11 but has neither `pip`, `pytest`, nor the application
dependencies installed, so the production handlers cannot be imported here.
This is an environment prerequisite failure, not an evaluation assertion
failure; no scenario executed and no application behavior is claimed as
passing from this attempt.

Static validation that does not import application dependencies completed:

```bash
python3 -m py_compile evals/__init__.py evals/offline.py \
  evals/test_offline_evals.py evals/run_evals.py
git diff --check
```

Both exited successfully. After the repository's documented dependency install,
rerun the command above to produce the scenario-level `unittest` evidence.
