"""Unit tests for the pure log-parsing core. No AI, no network — runs offline."""

from scripts.logparse import first_failure, parse_failures

GREEN_LOG = """\
============================= test session starts ==============================
collected 2 items

tests/test_calculator.py ..                                              [100%]

============================== 2 passed in 0.01s ===============================
"""

RED_LOG = """\
============================= test session starts ==============================
collected 2 items

tests/test_calculator.py F.                                              [100%]

=================================== FAILURES ===================================
___________________________________ test_add __________________________________
    def test_add():
>       assert add(2, 3) == 5
E       assert -1 == 5

tests/test_calculator.py:5: AssertionError
=========================== short test summary info ============================
FAILED tests/test_calculator.py::test_add - assert -1 == 5
========================= 1 failed, 1 passed in 0.02s ==========================
"""


def test_green_log_has_no_failures():
    assert parse_failures(GREEN_LOG) == []
    assert first_failure(GREEN_LOG) is None


def test_red_log_extracts_failure():
    failure = first_failure(RED_LOG)
    assert failure == {
        "file": "tests/test_calculator.py",
        "test": "test_add",
        "message": "assert -1 == 5",
    }


def test_failed_line_without_message_still_parses():
    log = "FAILED tests/test_widget.py::test_render"
    assert parse_failures(log) == [
        {"file": "tests/test_widget.py", "test": "test_render", "message": ""}
    ]


def test_multiple_failures_are_all_returned():
    log = (
        "FAILED tests/a.py::test_one - boom\n"
        "FAILED tests/b.py::test_two - kaboom\n"
    )
    failures = parse_failures(log)
    assert [f["test"] for f in failures] == ["test_one", "test_two"]
