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

VERSION = "0.4.0"

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
        """Raise BindingError if this build is not what the consumer pinned.

        Both the version and the code hash are required, as CONSTITUTION.md
        section 7 says. A pin with no hash is refused here rather than
        accepted as a weaker pin: a consumer that records only a version
        cannot detect changed code under the same version number.
        """
        if self.version != VERSION:
            raise BindingError(
                f"{self.consumer}: pinned HERALD {self.version}, running {VERSION}. "
                "Upgrading is an explicit act: re-run your calibration set, then re-pin."
            )
        if self.pinned_hash is None:
            raise BindingError(
                f"{self.consumer}: no code hash pinned. A version-only pin does not "
                "detect changed code; pin the code hash too (herald.binding.current_pin "
                "records both)."
            )
        actual = code_hash()
        if actual != self.pinned_hash:
            raise BindingError(
                f"{self.consumer}: HERALD {VERSION} source changed since pinning "
                f"(pinned {self.pinned_hash[:12]}, running {actual[:12]}). "
                "Same version, different code. Re-validate before re-pinning."
            )

    def verify_version_only_LEGACY(self) -> None:
        """The old, weaker check: version only, any code hash accepted.

        Kept so an existing consumer can move off it deliberately. It is not
        used by build(), read() or require_pin(), and it is named so that
        calling it cannot be mistaken for the required check. Do not use it
        for a consumer that handles consequential claims.
        """
        if self.version != VERSION:
            raise BindingError(
                f"{self.consumer}: pinned HERALD {self.version}, running {VERSION}. "
                "Upgrading is an explicit act: re-run your calibration set, then re-pin."
            )

    def is_hash_pinned(self) -> bool:
        return self.pinned_hash is not None


def current_pin(consumer: str) -> Binding:
    """A Binding for this exact build, for a consumer recording a fresh pin."""
    return Binding(consumer=consumer, version=VERSION, pinned_hash=code_hash())


def require_pin(consumer: str, version: str, pinned_hash: Optional[str]) -> Binding:
    """The enforcing form of a pin: a consumer calls this once at startup.

    Binding.verify() accepts a version-only pin and reports it as weaker.
    A consumer handling consequential claims should not be able to run on
    that weaker pin by accident, so this refuses a missing hash outright,
    then verifies version and code hash. It returns the verified Binding.
    """
    if not pinned_hash:
        raise BindingError(
            f"{consumer}: no code hash pinned. A version-only pin does not "
            "detect changed code; pin the code hash too."
        )
    binding = Binding(consumer=consumer, version=version, pinned_hash=pinned_hash)
    binding.verify()
    return binding


def main(argv: Optional[List[str]] = None) -> int:
    """Command line: ``python -m herald.binding show`` prints this build's
    version and code hash for recording a pin; ``python -m herald.binding
    check CONSUMER VERSION HASH`` exits 0 if the running build matches the
    pin and 1 (with the reason) if not. Meant for a consumer's startup
    script or CI step, so a moved build fails loudly instead of silently."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["show"]:
        print(f"version={VERSION}\ncode_hash={code_hash()}")
        return 0
    if len(args) == 4 and args[0] == "check":
        try:
            require_pin(args[1], args[2], args[3])
        except BindingError as exc:
            print(f"PIN FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"pin ok: {args[1]} on HERALD {args[2]}")
        return 0
    print("usage: python -m herald.binding show | check CONSUMER VERSION HASH", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
