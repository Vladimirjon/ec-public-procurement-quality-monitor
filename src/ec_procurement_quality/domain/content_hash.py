"""Value object identifying content by its SHA-256 digest."""

import hashlib
import re
from dataclasses import dataclass
from typing import Self

_SHA256_HEXDIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ContentHash:
    """A validated, immutable lowercase SHA-256 hexadecimal digest."""

    hexdigest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.hexdigest, str)
            or _SHA256_HEXDIGEST.fullmatch(self.hexdigest) is None
        ):
            raise ValueError(
                "a content hash must be exactly 64 lowercase hexadecimal characters"
            )

    @classmethod
    def of(cls, content: bytes) -> Self:
        """Compute the SHA-256 digest of exact content bytes."""
        return cls(hashlib.sha256(content).hexdigest())
