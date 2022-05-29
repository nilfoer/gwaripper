import pytest

# need to register custom marks (in conftest.py? didn't work in test_.. file)
# pytest_configure is automatically called
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "dltest: tests downloading audio files, which takes several minutes"
    )
    config.addinivalue_line(
        "markers",
        "sgasm: for disabling online sgasm tests if it is slow/offline"
    )
