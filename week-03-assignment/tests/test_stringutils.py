from src.stringutils import reverse, is_palindrome

def test_reverse():
    assert reverse("hello") == "olleh"

def test_is_palindrome():
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False
