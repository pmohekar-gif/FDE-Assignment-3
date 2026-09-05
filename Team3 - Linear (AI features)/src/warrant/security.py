from __future__ import annotations

import hashlib
import hmac
import html
import math
import re
import time
from dataclasses import dataclass

SECRET_NAME_ALTERNATIVES = (
    r"passwd|password|secret|api[_-]?key|apikey|access[_-]?key|private[_-]?key"
    r"|credentials?|client[_-]?secret|auth[_-]?token|token"
)
# Ordered: structural/high-confidence shapes first so that a broader pattern
# (email, card PAN) cannot consume part of a credential before it is classified.
SECRET_PATTERNS = [
    (
        "pem_block",
        re.compile(r"-----BEGIN [A-Z0-9 ]{2,40}-----[\s\S]{0,8000}?-----END [A-Z0-9 ]{2,40}-----"),
    ),
    (
        "connection_string",
        re.compile(
            r"\b[a-z][a-z0-9+.-]{1,20}://[^\s:@/'\"]{1,64}:[^\s:@/'\"]{1,128}@[^\s/'\"]{1,255}"
        ),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}")),
    (
        "secret_assignment",
        re.compile(
            r"\b[A-Za-z0-9_.-]{0,40}(?:" + SECRET_NAME_ALTERNATIVES + r")"
            r"\s*(?:=>|:=|=|:)\s*"
            r"(?:\"[^\"\n]{4,200}\"|'[^'\n]{4,200}'|`[^`\n]{4,200}`|[^\s,;)\]}]{8,200})",
            re.I,
        ),
    ),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I)),
    ("api_key", re.compile(r"\b(?:sk|ghp|lin_api)_[A-Za-z0-9_-]{12,}\b")),
    ("card_pan", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]
INJECTION_PATTERNS = [
    (re.compile(r"ignore (?:all |any )?(?:prior|previous|system) instructions", re.I), 1.0),
    (re.compile(r"\bSYSTEM\s*(?:NOTE|PROMPT|MESSAGE)?\s*:", re.I), 0.8),
    (re.compile(r"classif(?:y|ication).*\bALLOW\b", re.I), 1.0),
    (re.compile(r"(?:skip|bypass|disable).{0,30}(?:approval|policy|review)", re.I), 0.9),
    (re.compile(r"does not require (?:approval|review)", re.I), 0.7),
]


@dataclass(frozen=True)
class NormalisedContent:
    text: str
    redactions: list[dict[str, str | int]]
    injection_score: float
    injection_matches: list[str]


def redact_secrets(text: str) -> str:
    """Redact every known credential shape in place, keeping the surrounding text citable."""
    for name, pattern in SECRET_PATTERNS:
        text = pattern.sub(f"[REDACTED:{name.upper()}]", text)
    return text


def normalise_untrusted(title: str, body: str) -> NormalisedContent:
    text = html.unescape(f"{title}\n\n{body}")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    receipts: list[dict[str, str | int]] = []
    for name, pattern in SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            receipts.append({"type": name, "count": len(matches)})
            text = pattern.sub(f"[REDACTED:{name.upper()}]", text)
    hits: list[str] = []
    miss_probability = 1.0
    for pattern, weight in INJECTION_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
            miss_probability *= 1.0 - weight
    score = round(min(1.0, 1.0 - miss_probability), 3) if hits else 0.0
    return NormalisedContent(
        text=text, redactions=receipts, injection_score=score, injection_matches=hits
    )


def sign_webhook(secret: str, timestamp: str, raw_body: bytes) -> str:
    payload = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_webhook(secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    expected = sign_webhook(secret, timestamp, raw_body)
    return hmac.compare_digest(expected, signature)


def stable_vector(text: str, dimensions: int = 64) -> list[float]:
    """Local deterministic semantic-ish vector used only by fixture/offline mode."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9_/.-]+", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[slot] += sign * (1.0 + min(len(token), 12) / 12)
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))
