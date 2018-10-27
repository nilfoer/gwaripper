import pytest
import shutil
import os

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


def build_test_dir_furl(rel_path):
    conv_slashes = TESTS_DIR.replace("\\", "/")
    return f"file:///{conv_slashes}/{rel_path}"


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