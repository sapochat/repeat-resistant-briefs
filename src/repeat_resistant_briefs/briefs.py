from __future__ import annotations
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "ref", "source")

def canonical_url(url: str) -> str:
    raw = url.strip()
    parts = urlsplit(raw)
    if not parts.netloc:
        parts = urlsplit(f"https://{raw.lstrip('/')}")
    scheme = parts.scheme.lower() or "https"
    try:
        port = parts.port
    except ValueError:
        netloc = parts.netloc.lower().removeprefix("www.")
    else:
        host = (parts.hostname or "").lower().removeprefix("www.")
        if ":" in host:
            host = f"[{host}]"
        default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        netloc = host if port is None or default_port else f"{host}:{port}"
    path = parts.path.rstrip("/") or "/"
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith(TRACKING_PREFIXES)]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))

def identity(item: dict) -> str:
    return item.get("id") or canonical_url(item["url"])

def select_candidates(candidates: list[dict], history: list[dict], limit: int = 8) -> tuple[list[dict], list[dict]]:
    seen = {h.get("id") or canonical_url(h["url"]) for h in history}
    selected, suppressed = [], []
    for item in candidates:
        row = dict(item); row["canonical_url"] = canonical_url(item["url"]); row["identity"] = identity(item)
        repeated = row["identity"] in seen
        if repeated and not str(row.get("follow_up_reason", "")).strip():
            row["suppression_reason"] = "recently delivered without a concrete follow-up"
            suppressed.append(row); continue
        row["repeat"] = repeated
        row["score"] = float(row.get("quality", 0)) * 0.55 + float(row.get("relevance", 0)) * 0.45
        selected.append(row)
    selected.sort(key=lambda x: (x["score"], not x["repeat"]), reverse=True)
    return selected[:limit], suppressed

def build_source_pack(candidates: list[dict], history: list[dict], limit: int = 8) -> str:
    selected, suppressed = select_candidates(candidates, history, limit)
    lines = ["# Source Pack", "", "## Editorial rules", "", "- Do not mention this source pack or candidate scores in the delivered brief.", "- Reuse a recent item only for a concrete development or changed implication.", "- Omit weak sections rather than padding them.", "", "## Selected candidates", ""]
    for item in selected:
        repeat = " — FOLLOW-UP" if item["repeat"] else ""
        lines += [f"### [{item['title']}]({item['canonical_url']}){repeat}", f"- Source: {item.get('source','unknown')}", f"- Score: {item['score']:.2f}", f"- Substance: {item.get('substance','').strip()}"]
        if item.get("follow_up_reason"): lines.append(f"- Follow-up reason: {item['follow_up_reason'].strip()}")
        lines.append("")
    lines += ["## Suppressed recent items", ""]
    if not suppressed: lines.append("- None")
    for item in suppressed: lines.append(f"- {item['title']}: {item['suppression_reason']}")
    return "\n".join(lines).rstrip() + "\n"
