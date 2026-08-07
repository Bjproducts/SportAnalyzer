"""Text normalisation helpers.

Player search has to work for people who type ``odegaard`` when the database
holds ``Ødegaard``, or ``mbappe`` for ``Mbappé``.  Names are therefore stored
twice: the display form, and a folded ``search_name`` used for matching.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that unicode decomposition cannot split into base + accent.
_MANUAL_FOLDINGS = str.maketrans(
    {
        "ø": "o",
        "Ø": "o",
        "đ": "d",
        "Đ": "d",
        "ð": "d",
        "Ð": "d",
        "þ": "th",
        "Þ": "th",
        "ß": "ss",
        "æ": "ae",
        "Æ": "ae",
        "œ": "oe",
        "Œ": "oe",
        "ł": "l",
        "Ł": "l",
        # Turkish dotless i. The visual similarity to "i" is precisely the
        # reason it needs folding, so the ambiguous-character lint is wrong here.
        "ı": "i",  # noqa: RUF001
    }
)

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str | None) -> str:
    """Fold a name into a lowercase, accent-free, single-spaced search key.

    ``normalize_name("Martin Ødegaard")`` -> ``"martin odegaard"``
    ``normalize_name("Kylian Mbappé")``   -> ``"kylian mbappe"``
    ``normalize_name("N'Golo Kanté")``    -> ``"n golo kante"``

    Punctuation collapses to a single space rather than being deleted, so
    ``O'Brien`` and ``O Brien`` normalise identically.
    """
    if not value:
        return ""

    folded = value.translate(_MANUAL_FOLDINGS)
    # NFKD splits "é" into "e" + combining acute, which the category filter drops.
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.casefold()
    collapsed = _NON_ALPHANUMERIC.sub(" ", lowered)
    return collapsed.strip()


def search_tokens(value: str | None) -> list[str]:
    """Split a normalised name into its individual words."""
    normalized = normalize_name(value)
    return normalized.split() if normalized else []
