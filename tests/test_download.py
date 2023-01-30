import pytest

import os
import gwaripper.config as cfg

from gwaripper.cli import _cl_link
from utils import TESTS_DIR, setup_tmpdir_param, gen_hash_from_file

class ArgsDummy:
    def __init__(self, links):
        assert(type(links) is list)
        self.links = links
        self.download_duplicates = True

@pytest.mark.dltest
def test_download_hls(setup_tmpdir_param):
    # NOTE: not deterministic?
    expected_md5 = ("c5d91cb3d0fd7340479f22232115111f", "cf2fe1a305f6128ae0c9893b91178212")

    testpath = setup_tmpdir_param
    cfg.set_root(testpath)
    _cl_link(ArgsDummy(["https://erocast.me/track/420/promise-that-i-got-you"]))

    expected_fn = os.path.join(testpath, "BonSoirAnxiety", "Promise That I Got You.mp4")
    assert gen_hash_from_file(expected_fn, "md5", _hex=True) in expected_md5

