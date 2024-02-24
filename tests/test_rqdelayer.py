import pytest
import time
from gwaripper.utils import RequestDelayer

@pytest.fixture
def create_rqdelayer():
    # delays request by .25 when last one was less than 1 sec ago
    r1 = RequestDelayer(0.25, 1)
    # delays request by .25 when last delay was more than 3 sec ago
    r2 = RequestDelayer(0.25, 3, mode="last-delay")
    yield r1, r2
    del r1, r2


def test_rqd_delay(create_rqdelayer):
    r1, r2 = create_rqdelayer

    for i in range(1, 14, 3):
        time.sleep(i/10)
        b4 = time.time()
        r1.delay_request()
        after = time.time()
        # we dont sleep on first req
        if i != 1 and i < 10:
            assert 0.3 > (after - b4) > 0.25
        else:
            assert (after - b4) < 0.05

    # for i in range(1, 14, 3):
    #     b4 = time.time()
    #     r1.last_request = b4 - i/10  # not using sleep but assigning last time directly
    #     r1.delay_request()
    #     after = time.time()
    #     if i < 10:
    #         assert 0.3 > (after - b4) > 0.25
    #     else:
    #         assert after == b4

    for i in [0, 1, 2.5, .2]:
        # sleep at i=0 (first req) and i=2.5 (slept 3.5sec)
        time.sleep(i)
        b4 = time.time()
        r2.delay_request()
        after = time.time()
        if i in (0, 2.5):
            assert 0.3 > (after - b4) > 0.25
        else:
            assert (after - b4) < 0.05
