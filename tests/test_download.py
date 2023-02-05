import pytest

import os
import gwaripper.config as cfg

from gwaripper.gwaripper import GWARipper
from gwaripper.info import FileInfo
from gwaripper.cli import _cl_link
from gwaripper.download import DownloadErrorCode
from utils import TESTS_DIR, setup_tmpdir_param, gen_hash_from_file

class ArgsDummy:
    def __init__(self, links, **kwargs):
        assert(type(links) is list)
        self.links = links
        self.download_duplicates = True
        self.__dict__.update(kwargs)

@pytest.mark.dltest
def test_download_hls(setup_tmpdir_param):
    # NOTE: not deterministic?
    expected_md5 = ("c5d91cb3d0fd7340479f22232115111f", "cf2fe1a305f6128ae0c9893b91178212")

    testpath = setup_tmpdir_param
    cfg.set_root(testpath)
    _cl_link(ArgsDummy(["https://erocast.me/track/420/promise-that-i-got-you"]))

    expected_fn = os.path.join(testpath, "BonSoirAnxiety", "Promise That I Got You.mp4")
    assert gen_hash_from_file(expected_fn, "md5", _hex=True) in expected_md5

def test_skip_non_audio_default(monkeypatch, setup_tmpdir_param):
    testpath = setup_tmpdir_param

    gwa = GWARipper()
    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._download_file_http", lambda *args: None)
    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._add_to_db", lambda *args: 13)
    files = [
        FileInfo(None, True, "mp3", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, False, "jpg", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, True, "m4a", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, True, "mp4", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, False, "png", "ksdjfks", "sfdkfs", *[None]*4),
    ]
    for f in files:
        gwa.download(f)
        assert f.downloaded is DownloadErrorCode.DOWNLOADED

def test_skip_non_audio(monkeypatch, setup_tmpdir_param):
    testpath = setup_tmpdir_param

    gwa = GWARipper(skip_non_audio=True)
    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._download_file_http", lambda *args: None)
    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._add_to_db", lambda *args: 13)
    files = [
        FileInfo(None, True, "mp3", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, False, "jpg", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, True, "m4a", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, True, "mp4", "ksdjfks", "sfdkfs", *[None]*4),
        FileInfo(None, False, "png", "ksdjfks", "sfdkfs", *[None]*4),
    ]
    for f in files:
        gwa.download(f)
        if f.is_audio:
            assert f.downloaded is DownloadErrorCode.DOWNLOADED
        else:
            assert f.downloaded is DownloadErrorCode.NOT_DOWNLOADED
