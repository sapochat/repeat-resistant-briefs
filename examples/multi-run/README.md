# Three-run example

This example demonstrates why ranking alone cannot prevent repetition.

- **Day 1:** three genuinely new signals are selected.
- **Day 2:** Alpha repeats without a material change and is suppressed. Beta repeats but survives because a published correction changes the conclusion. Delta is new.
- **Day 3:** another Beta recap is suppressed because it adds no new evidence. Epsilon is new and selected.

Run it after installing the package:

```bash
.venv/bin/python examples/multi-run/run.py
```

Generated source packs and `summary.json` are committed under `output/` so the behavior is inspectable without running anything.
