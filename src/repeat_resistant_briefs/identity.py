"""URL identities; conservative-v1 only removes utm_*, fbclid and gclid.

Legacy additionally drops www, terminal slashes and fragments and sorts queries.
Neither profile treats arbitrary ref/source parameters as tracking.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = frozenset({'fbclid', 'gclid'})
CANONICALIZATION_VERSION = 'conservative-v1'


def canonical_url(url: str, profile: str = 'legacy') -> str:
    """Public legacy default retained for compatibility; new selection is conservative."""
    if profile not in ('conservative', 'legacy'):
        raise ValueError('unknown canonicalization profile')
    if not isinstance(url, str) or not url.strip():
        raise ValueError('url must be a nonblank string')
    if any(ord(c) < 32 or ord(c) == 127 for c in url) or '\\' in url:
        raise ValueError('url contains control characters or backslashes')
    if any(c.isspace() for c in url):
        raise ValueError('URL contains literal whitespace')
    if re.search(r'%(?![0-9A-Fa-f]{2})', url):
        raise ValueError('URL contains malformed percent escape')
    raw = url
    if '://' not in raw:
        if raw.startswith('//'):
            raw = 'https:' + raw
        elif re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', raw) and not re.match(r'^[^/:]+:[0-9]+(?:/|$)', raw):
            raise ValueError('unsupported URL scheme')
        else:
            raw = 'https://' + raw
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() not in ('http', 'https'):
            raise ValueError('unsupported URL scheme')
        if not parts.netloc or parts.username is not None or parts.password is not None:
            raise ValueError('URL requires a host and forbids credentials')
        if parts.netloc.endswith(':'):
            raise ValueError('empty URL port')
        port = parts.port
        host = parts.hostname or ''
        if ':' in host:
            ipaddress.IPv6Address(host)
            host = '[' + host.lower() + ']'
        else:
            host = host.encode('idna').decode('ascii').lower()
            labels = host.rstrip('.').split('.')
            if len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
                raise ValueError('malformed URL host')
            if re.fullmatch(r'[0-9.]+', host):
                ipaddress.IPv4Address(host)
        if profile == 'legacy':
            host = host.removeprefix('www.')
        scheme = parts.scheme.lower()
        netloc = host if port is None or (scheme, port) in (('http',80),('https',443)) else f'{host}:{port}'
        kept = []
        for pair in parts.query.split('&'):
            key = unquote_plus(pair.split('=',1)[0]).lower()
            if not key.startswith('utm_') and key not in TRACKING_KEYS:
                kept.append(pair)
        query = '&'.join(kept)
        path, fragment = parts.path, parts.fragment
        if profile == 'legacy':
            path = path.rstrip('/') or '/'
            fragment = ''
            query = urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
        return urlunsplit((scheme, netloc, path, query, fragment))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'invalid URL: {exc}') from exc


def identity(item: dict, profile: str = 'legacy') -> str:
    return item.get('id') or canonical_url(item['url'], profile)


def matches(left: dict, right: dict) -> bool:
    """Direct typed ID OR canonical URL match; never transitive union-find."""
    return bool(left.get('id') is not None and left.get('id') == right.get('id')) or left['canonical_url'] == right['canonical_url']
