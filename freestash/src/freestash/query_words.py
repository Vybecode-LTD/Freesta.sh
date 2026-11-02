"""Query words that pick categories: "medieval sword sfx" searches "medieval sword" in Audio.

The words live in shared/categories.json (exported to categories_data.py), so the web, the desktop, the CLI and MCP
read a query the same way. The apps show each pick as a chip; removing it sends the word back in `keep`, because
"sound" or "photo" can be the subject too. Contract: dev plans/contracts/grouped-results.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from freestash.categories_data import CATEGORIES, PACK_WORDS
from freestash.models import MediaType, ParsedQuery, QueryPick

FILLER = frozenset({"a", "an", "the", "of", "for", "with", "and", "or"})
MAX_PHRASE = 3
_PUNCT = ".,;:!?\"'()[]{}"

# A word picks a category, or (None) turns packs on: "sfx pack" (contract packs-and-new-kinds)
WORDS: dict[str, MediaType | None] = {**{w: MediaType(c["id"]) for c in CATEGORIES for w in c["words"]},
                                      **dict.fromkeys(PACK_WORDS)}
ORDER: dict[MediaType, int] = {MediaType(c["id"]): i for i, c in enumerate(CATEGORIES)}


def _norm(token: str) -> str:
    return token.strip(_PUNCT).lower()


def parse_query(text: str, keep: Iterable[str] = ()) -> ParsedQuery:
    """Read category and pack words out of `text`. Words in `keep` (any case) stay in the query. Pure."""
    kept = {" ".join(_norm(t) for t in k.split()) for k in keep}  # a chip's word comes back as typed: "SFX!"
    tokens = text.split()
    norm = [_norm(t) for t in tokens]
    rest: list[str] = []
    picks: list[QueryPick] = []
    i = 0
    while i < len(tokens):
        for n in range(min(MAX_PHRASE, len(tokens) - i), 0, -1):
            phrase = " ".join(norm[i:i + n])
            if phrase in WORDS:
                if phrase in kept:
                    rest += tokens[i:i + n]
                else:
                    kind = WORDS[phrase]
                    picks.append(QueryPick(word=" ".join(tokens[i:i + n]), media_type=kind, packs=kind is None))
                i += n
                break
        else:
            rest.append(tokens[i])
            i += 1
    if picks:
        while rest and _norm(rest[0]) in FILLER:
            rest.pop(0)
        while rest and _norm(rest[-1]) in FILLER:
            rest.pop()
    if not picks or not rest:  # nothing left to search for: read every word as a word
        return ParsedQuery(original=text, q=" ".join(tokens))
    media = sorted({p.media_type for p in picks if p.media_type}, key=ORDER.__getitem__)
    return ParsedQuery(original=text, q=" ".join(rest), media_types=media, packs=any(p.packs for p in picks),
                       picks=picks)
