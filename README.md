# Repeat-Resistant Briefs

A deterministic source-pack builder for recurring AI-assisted reports and newsletters.

The failure this addresses is subtle: every run is technically fresh, but the same popular links keep reappearing. Ranking alone cannot fix that. The writer needs recent delivered-output history, canonical identities, and an explicit reason to revisit an item.

## Data flow

```text
candidate sources → normalize and score → compare with delivered history
→ suppress unjustified repeats → source pack → human/agent synthesis → delivered history
```

## Three-run demonstration

The committed [`examples/multi-run`](examples/multi-run/) sequence shows the stateful behavior across three reporting days:

- a popular item repeating without new evidence is suppressed;
- a repeated benchmark survives when a correction materially changes the conclusion;
- the same benchmark is suppressed again when the next mention is only a recap.

Each run produces an inspectable source pack and a machine-readable summary.

## Install and run the example

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/repeat-resistant-briefs \
  examples/candidates.json examples/history.json /tmp/source-pack.md

.venv/bin/python -m unittest discover -s tests -v
```

Candidates may include `follow_up_reason`; repeated items are admitted only when that reason is concrete. The output is a source pack, not a finished newsletter.

MIT licensed.
