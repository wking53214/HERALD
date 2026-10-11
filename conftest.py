"""No skipped tests. Enforced, not asked for.

WHY THIS FILE EXISTS

A skipped test reports success and verifies nothing, and the failure mode
is not that it never runs. It is that it stops failing when the thing it
skipped for goes away.

HERALD carried 25 skips under a documented convention that "a skip is not a
pass, it is a recorded gap." One of them asserted that authorization
continuity was unreachable at the package's own surface. By the time anyone
looked, `GateDecision` had grown `authorized_content_hash` and an
`authorization_mac` over it, `verify_against` raised on a mismatch, and the
gap had been closed for an unknown number of commits. The skip did not
notice, because a skip cannot notice. Twenty-two more were hiding a real
security property -- that out-of-scope text yields no claim for an attack
to act on -- which caught nothing until it was written as an assertion.

So: if you need to record a gap, assert it. An assertion fails the day the
gap closes and makes someone write the real test. That is the whole
argument, and this file is it in executable form.

WHAT IT FAILS ON

All four ways a test can decline to run: `pytest.skip()`,
`@pytest.mark.skip`, `@pytest.mark.skipif`, `pytest.importorskip`.

And XPASS, which is the same disease in a different marker. A test marked
expected-to-fail that now passes is a marker that outlived its premise,
exactly like the R2 skip above, and it also reports green.

WHAT IT ONLY REPORTS

XFAIL. An xfail runs, and it fails, and that was the declared expectation,
so it is not a test declining to run and this file does not block on it.
It is listed anyway, because a suite reporting green while carrying known
failures is worth seeing every run rather than discovering later.

`-p no:skipping` is not sufficient and was tried first. On a fixture of
four skips it converted two, left two, and exited 0.

INSTALLING IT

Drop into the repository root as `conftest.py`, or paste into an existing
one. No dependencies, no configuration, nothing to remember. There is no
allowlist on purpose: an allowlist is a convention, and a convention is
what failed.

If a test genuinely cannot run in this environment, it does not belong in
the suite as a skip. Either assert the absence it is waiting on, move it
behind a real capability check that fails loudly, or delete it.
"""

from __future__ import annotations

import importlib.util
from typing import Any, List, Tuple

# Collect the connector tests only when CNS is installed, and the absence tests
# only when it is not. Ignoring a file is not a skip, so neither set declines.
if importlib.util.find_spec("cns") is not None:
    collect_ignore = ["Tests/test_cns_absent.py"]
else:
    collect_ignore = ["Tests/test_cns_connector.py"]

_DECLINED: List[Tuple[str, str, str]] = []
_XFAILED: List[Tuple[str, str]] = []


def pytest_runtest_logreport(report: Any) -> None:
    """Record anything that declined to run, or that passed while marked to fail."""
    if report.skipped:
        if hasattr(report, "wasxfail"):
            # Ran, failed, was expected to. Reported, never fatal.
            _XFAILED.append((report.nodeid, str(report.wasxfail or "")))
            return
        # report.longrepr is (path, lineno, "Skipped: reason") for a skip.
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2])
        else:
            reason = str(report.longrepr or "")
        _DECLINED.append(("SKIP", report.nodeid, reason))
    elif report.when == "call" and report.passed and hasattr(report, "wasxfail"):
        _DECLINED.append((
            "XPASS", report.nodeid,
            "marked expected-to-fail but passed: the marker outlived its premise",
        ))


def pytest_terminal_summary(terminalreporter: Any, *args: Any, **kwargs: Any) -> None:
    w = terminalreporter
    if _XFAILED:
        w.section("known failures carried by this suite (not fatal)", sep="-",
                  yellow=True)
        for nodeid, reason in _XFAILED:
            w.line(f"  XFAIL  {nodeid}")
            if reason:
                w.line(f"         {reason.strip()[:200]}")
    if not _DECLINED:
        return
    w.section("tests that declined to run", sep="=", red=True, bold=True)
    for kind, nodeid, reason in _DECLINED:
        w.line(f"  {kind}  {nodeid}")
        if reason:
            w.line(f"        {reason.strip()[:220]}")
    w.line("")
    w.line("A skipped test reports success and verifies nothing, and stops")
    w.line("failing when the thing it skipped for goes away. Assert the gap")
    w.line("instead: an assertion fails the day the gap closes.")


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Fail the run. Without this the suite reports green and CI believes it."""
    if _DECLINED and exitstatus == 0:
        session.exitstatus = 1
