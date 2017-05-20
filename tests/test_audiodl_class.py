import pytest
import os
import hashlib
import pandas as pd
from gwaripper.gwaripper import AudioDownload

# mark module with dltest, all classes, funcs, methods get marked with that
# usable on single classes/funcs.. with @pytest.mark.webtest
# You can then restrict a test run to only run tests marked with dltest:
# $ pytest -v -m dltest
pytestmark = pytest.mark.dltest

testdir = os.path.normpath("N:\\_archive\\test\\trans\soundgasmNET\\_dev\\_sgasm-repo\\tests\\test_dl")

urls = [
        ("sgasm", "https://soundgasm.net/u/miyu213/F4M-Im-your-Pornstar-Cumdumpster-Slut-Mother-RapeBlackmailFacefuckingSlap-my-face-with-that-thick-cockInnocent-to-sluttyRoughDirty-TalkFuck-Me-Into-The-MatressCreampieImpregMultiple-Real-Orgasms"),
        ("chirb.it", "http://chirb.it/s80vbt"),
        ("eraudica", "https://www.eraudica.com/e/eve/2015/Twin-TLC-Dr-Eve-and-Nurse-Eve-a-Sucking-Fucking-Hospital-Romp")
    ]

r_infos = [{
        "r_user": "test_user",
        "title": "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][incest][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Denial][Toys][Mast][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]",
        "selftext": "Testing selftext"
    },
    {
        "r_user": "test_user",
        "title": "[FF4M] It's not what you think, brother! [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with /u/alwaysslightlysleepy]",
        "selftext": "Testing selftext"
    },
    {
        "r_user": "test_user",
        "title": "[F4M] Nurse Eve and Dr. Eve Double Team TLC! [twins][binaural][medical][sucking and licking and fucking and cumming!][face sitting][riding your cock] [repost]",
        "selftext": "Testing selftext"
    }]

# we could either use a predefined fixture by pytest to get a unique tmpdir with def gen_audiodl_sgasm(tmpdir)
# and then use tmpdir.strpath as path or we use a test dir thats always the same, and make sure to clean up after
# with tmpdir sth like this could be avoided: test_audiodl_class.py::test_chirbit FAILED self = Index([], dtype='object'), key = 'URL',
# -> file wasnt deleted last time so download method tried to set missing values on df -> failed
@pytest.fixture
def gen_audiodl_sgasm():


    a = AudioDownload(urls[0][1], urls[0][0], r_infos[0])
    # Der benötigte Wert wird mit yield zurückgegeben. So ist es möglich, dass nach dem yield-Statement
    # die Fixture wieder abgebaut werden kann
    yield a, testdir

    # clean up
    # since a has been modified since we yielded, we can use a.filename.. etc
    # del audio, selftext and folder
    os.remove(os.path.join(testdir, a.name_usr, a.filename_local))
    os.remove(os.path.join(testdir, a.name_usr, a.filename_local + ".txt"))
    os.rmdir(os.path.join(testdir, a.name_usr))
    del a


@pytest.fixture
def gen_audiodl_chirbit():
    a = AudioDownload(urls[1][1], urls[1][0], r_infos[1])

    yield a, testdir

    os.remove(os.path.join(testdir, a.name_usr, a.filename_local))
    os.remove(os.path.join(testdir, a.name_usr, a.filename_local + ".txt"))
    os.rmdir(os.path.join(testdir, a.name_usr))
    del a


@pytest.fixture
def gen_audiodl_eraudica(tmpdir):
    a = AudioDownload(urls[2][1], urls[2][0], r_infos[2])

    yield a, testdir

    os.remove(os.path.join(testdir, a.name_usr, a.filename_local))
    os.remove(os.path.join(testdir, a.name_usr, a.filename_local + ".txt"))
    os.rmdir(os.path.join(testdir, a.name_usr))
    del a


def md5(fname):
    # construct a hash object by calling the appropriate constructor function
    hash_md5 = hashlib.md5()
    # open file in read-only byte-mode
    with open(fname, "rb") as f:
        # only read in chunks of size 4096 bytes
        for chunk in iter(lambda: f.read(4096), b""):
            # update it with the data by calling update() on the object
            # as many times as you need to iteratively update the hash
            hash_md5.update(chunk)
    # get digest out of the object by calling digest() (or hexdigest() for hex-encoded string)
    return hash_md5.hexdigest()



def test_soundgasm(gen_audiodl_sgasm):
    fn = "[F4M] I_m your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]"[0:110] + ".m4a"
    a, dir = gen_audiodl_sgasm
    a.call_host_get_file_info()
    # all info is correct
    assert a.url_to_file == "https://soundgasm.net/sounds/e764a6235fa9ca5e23ee10b3989721d97fc7242d.m4a"
    assert a.file_type == ".m4a"
    assert a.filename_local == fn
    assert a.title == "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]"
    assert a.descr == "Tribute to one of my listener, you know who you are, love <3"

    # download worked
    a.download(pd.DataFrame(), 0, 0, dir)
    assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert md5(os.path.join(dir, a.name_usr, fn)) == "60fec6dc98e1d16fb73fad2d31c50588"
    assert a.downloaded is True

    # selftext written correctly
    with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
        assert f.read() == "Testing selftext"


def test_chirbit(gen_audiodl_chirbit):
    fn = "[FF4M] It_s not what you think, brother_ [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with _u_alwaysslightlysleepy]"[0:110] + ".mp3"
    a, dir = gen_audiodl_chirbit
    a.call_host_get_file_info()
    # only compare till aws id other part of url changes every time
    assert a.url_to_file.split("&",1)[0] == "http://audio.chirbit.com/Pip_1446845763.mp3?AWSAccessKeyId=AKIAIHJD7T6NGQMM2VCA"
    assert a.file_type == ".mp3"
    assert a.filename_local == fn

    a.download(pd.DataFrame(), 0, 0, dir)
    assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert md5(os.path.join(dir, a.name_usr, fn)) == "e8ff0e482d1837cd8be723c64b3ae32f"
    assert a.downloaded is True

    with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
        assert f.read() == "Testing selftext"


def test_eraudica(gen_audiodl_eraudica):
    fn = "[F4M] Nurse Eve and Dr. Eve Double Team TLC_ [twins][binaural][medical][sucking and licking and fucking and cumming_][face sitting][riding your cock] [repost]"[0:110] + ".mp3"
    a, dir = gen_audiodl_eraudica
    a.call_host_get_file_info()
    assert a.url_to_file == "https://data1.eraudica.com/fd/71c71873-7356-4cee-bdfa-de1d0a652c3c_/Twins%20-%20Nurse%20Eve%20and%20Dr.%20Eve.mp3"
    assert a.file_type == ".mp3"
    assert a.filename_local == fn

    a.download(pd.DataFrame(), 0, 0, dir)
    assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert md5(os.path.join(dir, a.name_usr, fn)) == "b26ffe08e2068a822234a22aa7a7f40a"
    assert a.downloaded is True

    with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
        assert f.read() == "Testing selftext"