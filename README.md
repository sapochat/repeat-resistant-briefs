# Repeat-Resistant Briefs

A deterministic source-pack builder for recurring AI-assisted reports and newsletters.

The failure this addresses is subtle: every run is technically fresh, but the same popular links keep reappearing. Ranking alone cannot fix that. The writer needs recent delivered-output history, canonical identities, and an explicit reason to revisit an item.

## Data flow

```text
candidate sources → normalize and score → compare with delivered history
→ suppress unjustified repeats → source pack → human/agent synthesis → delivered history
```

## Run the example

```bash
PYTHONPATH=src python3 -m repeat_resistant_briefs.cli   examples/candidates.json examples/history.json /tmp/source-pack.md

python3 -m unittest discover -s tests -v
```

Candidates may include `follow_up_reason`; repeated items are admitted only when that reason is concrete. The output is a source pack, not a finished newsletter.

MIT licensed.
