"""Pure, dependency-free parsing of a pytest run log.

This is the unit-tested core of the build-fixer lab (mirrors the other
starters' "pure logic + heavier driver" split): it turns raw pytest output
into structured failure records using only the standard library, so it runs
under `make test` with no AI or network dependencies. The agent driver
(build_fixer_agent.py) builds on it but needs the `anthropic` SDK.
"""

import re

# Matches pytest's short-summary lines, e.g.
#   FAILED tests/test_calculator.py::test_add - assert -1 == 5
_FAILED_RE = re.compile(
    r"^FAILED\s+(?P<file>[^\s:]+)::(?P<test>[^\s-]+)(?:\s+-\s+(?P<message>.*))?$"
)


def parse_failures(log):
    """Return a list of {file, test, message} dicts, one per failed test.

    Reads the `FAILED <file>::<test> - <message>` lines pytest prints in its
    short test summary. Returns an empty list when the run is green.
    """
    failures = []
    for line in log.splitlines():
        match = _FAILED_RE.match(line.strip())
        if match:
            failures.append(
                {
                    "file": match.group("file"),
                    "test": match.group("test"),
                    "message": (match.group("message") or "").strip(),
                }
            )
    return failures


def first_failure(log):
    """Return the first failure record, or None if the run passed."""
    failures = parse_failures(log)
    return failures[0] if failures else None
