import pytest
import shutil
import os
import time
import hashlib
import random
import sqlite3

import gwaripper.config as config
from gwaripper.logging_setup import configure_logging

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))

configure_logging(os.path.join(TESTS_DIR, "gwaripper_tests.log"))


def build_file_url(abspath):
    conv_slashes = abspath.replace("\\", "/")
    return f"file:///{conv_slashes}"


@pytest.fixture
def setup_tmpdir():
    tmpdir = os.path.join(TESTS_DIR, "tmp")
    # we wont return after yielding if the test raises an exception
    # -> better way to delete at start of next test so we also
    # have the possiblity to check the content of tmpdir manually
    # -> but then we also have to except FileNotFoundError since tmpdir
    # might not exist yet
    try:
        shutil.rmtree(tmpdir)
    except FileNotFoundError:
        pass
    os.makedirs(tmpdir)

    config.ROOTDIR = tmpdir
    return tmpdir
    # yield tmpdir
    # # del dir and contents after test is done


@pytest.fixture
def setup_tmpdir_param():
    """
    For parametrized pytest fixtures and functions since pytest still accesses
    the tmp directory while switching between params which means we cant delete
    tmpdir -> we try to delete all dirs starting with tmp_ and then we
    create a new tmpdir with name tmp_i where i is the lowest number for which
    tmp_i doesnt exist
    """
    # maybe use @pytest.fixture(autouse=True) -> gets called before and after(with yield)
    # every test

    # we wont return after yielding if the test raises an exception
    # -> better way to delete at start of next test so we also
    # have the possiblity to check the content of tmpdir manually
    # -> but then we also have to except FileNotFoundError since tmpdir
    # might not exist yet
    tmpdir_list = [dirpath for dirpath in os.listdir(TESTS_DIR) if dirpath.startswith(
                   "tmp_") and os.path.isdir(os.path.join(TESTS_DIR, dirpath))]
    for old_tmpdir in tmpdir_list:
        try:
            shutil.rmtree(os.path.join(TESTS_DIR, old_tmpdir))
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    i = 0
    while True:
        tmpdir = os.path.join(TESTS_DIR, f"tmp_{i}")
        if os.path.isdir(tmpdir):
            i += 1
            continue
        os.makedirs(tmpdir)
        break

    return tmpdir


# we can init this class at start of a function and a failed test will
# be reproducable if we only use this class or it's rnd attrib to
# generate our testing input by reseeding with the printed seed
class RandomHelper():
    def __init__(self, seed=time.time()):
        print("SEEDING TESTING PRNG WITH:", seed)
        self.rnd = random.Random(seed)

    def random_string(
            self,
            length,
            chars="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefABCDEF"):
        return "".join(self.rnd.choices(chars, k=length))


def gen_hash_from_file(fname, hash_algo_str, _hex=True):
    # construct a hash object by calling the appropriate constructor function
    hash_obj = hashlib.new(hash_algo_str)
    # open file in read-only byte-mode
    with open(fname, "rb") as f:
        # only read in chunks of size 4096 bytes
        for chunk in iter(lambda: f.read(4096), b""):
            # update it with the data by calling update() on the object
            # as many times as you need to iteratively update the hash
            hash_obj.update(chunk)
    # get digest out of the object by calling digest() (or hexdigest() for hex-encoded string)
    if _hex:
        return hash_obj.hexdigest()
    else:
        return hash_obj.digest()


def get_all_rowtuples_db(filename, query_str):
    conn = sqlite3.connect(filename)
    c = conn.execute(query_str)
    rows = c.fetchall()
    conn.close()
    return rows
