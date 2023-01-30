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
    config.addinivalue_line(
        "markers",
        "broken_sites: enable to test extractors/downloads of broken sites: e.g. chirbit"
    )

    # only test broken sites if the --test-broken option was passed
    if not config.option.test_broken_sites:
        # append to config.option.markexpr so we don't overwrite exprs passed with -m
        setattr(config.option, 'markexpr',
                f"{config.option.markexpr}{' and ' if config.option.markexpr else ''}not broken_sites")

def pytest_addoption(parser):
    parser.addoption('--test-broken', action='store_true', dest="test_broken_sites",
                 default=False, help="enable testing of broken sites")
