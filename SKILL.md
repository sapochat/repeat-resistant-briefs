---
name: repeat-resistant-briefs
description: Use when a recurring report or newsletter keeps resurfacing the same links, repos, or themes. Build a deterministic source pack with canonical identities, recent delivery history, justified follow-ups, and quality-first selection.
version: 1.0.0
author: Santi Pochat and Janus
license: MIT
metadata:
  hermes:
    tags: [editorial, newsletter, reports, history, deduplication]
---

# Repeat-Resistant Briefs

1. Collect raw sources deterministically.
2. Normalize URLs and stable item identifiers.
3. Parse recent delivered outputs—not only raw candidate history.
4. Suppress items seen in the configured window unless a concrete follow-up reason exists.
5. Apply quality and relevance floors before source diversity.
6. Build a visible source pack containing candidates, recent-history warnings, and editorial rules.
7. Let a human or model synthesize only from the source pack.
8. QA the delivered response separately from prompt and collector wrappers.
9. Feed delivered identities back into history.

Do not use rigid source quotas to promote weak material. It is valid for a section or source to contribute zero items.
