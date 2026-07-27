"""A deliberately buggy calculator.

`add` is wrong on purpose: it subtracts instead of adding, so `test_add`
fails. That red build is what the Week 3 build-fixer agent detects, explains,
and proposes a fix for. `multiply` is correct and its test passes — proving the
agent targets only the failing code, not everything.
"""


def add(a, b):
    # Bug: subtraction instead of addition (the failing test catches this).
    return a - b


def multiply(a, b):
    return a + b
