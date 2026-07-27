from src.calculator import add, multiply


def test_add():
    assert add(2, 3) == 5  # FAILS until the agent's fix is applied (add returns -1)


def test_multiply():
    assert multiply(3, 4) == 12  # passes — the agent must leave this alone
