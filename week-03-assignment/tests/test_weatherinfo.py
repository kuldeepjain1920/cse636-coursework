from src.weatherinfo import get_status_code

def test_get_status_code():
    assert get_status_code("https://example.com") == 200
