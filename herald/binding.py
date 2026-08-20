"""
binding.py -- pinning a consumer to an exact build of this package.

THE RISK THIS ADDRESSES
------------------------
A shared interpretation layer means a shared blast radius. Today a bad
heuristic hurts one project. Centralize interpretation and one bad
extractor quietly corrupts inputs everywhere at once, which cuts against
the isolated-failure-domain property that makes modular specialization
worth having.

So consumers pin. Each project records the HERALD version and the code
hash it validated against, and refuses to run if either has moved. A fix
does not propagate silently; upgrading is an explicit act with a diff
attached to it. This is the same discipline the cassette code-hash bump
already enforces, applied to a dependency instead of a cassette.

WHAT THE CODE HASH COVERS
--------------------------
Every .py file in the package, by content, in sorted path order. Tests
are excluded: a new test does not change behaviour, and making test
authorship trigger a re-pin across every consuming project would teach
people to stop writing tests.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .errors import BindingError

VERSION = "0.3.0"

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _package_files() -> List[str]:
    return sorted(
        os.path.join(_PACKAGE_DIR, name)
        for name in os.listdir(_PACKAGE_DIR)
        if name.endswith(".py")
    )


def code_hash() -> str:
    """SHA-256 over the package's own source, path-ordered and content-keyed."""
    digest = hashlib.sha256()
    for path in _package_files():
        digest.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()


def file_hashes() -> Dict[str, str]:
    """Per-file digests, so an upgrade diff can name what actually moved."""
    out: Dict[str, str] = {}
    for path in _package_files():
        with open(path, "rb") as handle:
            out[os.path.basename(path)] = hashlib.sha256(handle.read()).hexdigest()
    return out


@dataclass(frozen=True)
class Binding:
    """One consumer's pin to a specific HERALD build.

    consumer     -- which project is pinning, e.g. "sentinel_os".
    version      -- the HERALD version that project validated against.
    pinned_hash  -- the code hash it validated against. None means the
                    consumer pinned the version only, which is weaker and
                    is reported as such rather than silently accepted.
    """

    consumer: str
    version: str
    pinned_hash: Optional[str] = None

    def verify(self) -> None:
        """Raise BindingError if this build is not what the consumer pinned."""
        if self.version != VERSION:
            raise BindingError(
                f"{self.consumer}: pinned HERALD {self.version}, running {VERSION}. "
                "Upgrading is an explicit act: re-run your calibration set, then re-pin."
            )
        if self.pinned_hash is None:
            return
        actual = code_hash()
        if actual != self.pinned_hash:
            raise BindingError(
                f"{self.consumer}: HERALD {VERSION} source changed since pinning "
                f"(pinned {self.pinned_hash[:12]}, running {actual[:12]}). "
                "Same version, different code. Re-validate before re-pinning."
            )

    def is_hash_pinned(self) -> bool:
        return self.pinned_hash is not None


def current_pin(consumer: str) -> Binding:
    """A Binding for this exact build, for a consumer recording a fresh pin."""
    return Binding(consumer=consumer, version=VERSION, pinned_hash=code_hash())
