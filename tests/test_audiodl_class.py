import pytest
import os
import hashlib
import sqlite3
from gwaripper.audio_dl import AudioDownload
from gwaripper.utils import InfoExtractingError

# mark module with dltest, all classes, funcs, methods get marked with that
# usable on single classes/funcs.. with @pytest.mark.webtest
# You can then restrict a test run to only run tests marked with dltest:
# $ pytest -v -m dltest
# pytestmark = pytest.mark.dltest  MODULE contains more than dltest now use function marker

testdir = os.path.normpath("N:\\_archive\\test\\trans\soundgasmNET\\_dev\\_sgasm-repo\\tests\\test_dl")

urls = [
        ("sgasm", "https://soundgasm.net/u/miyu213/F4M-Im-your-Pornstar-Cumdumpster-Slut-Mother-RapeBlackmailFacefuckingSlap-my-face-with-that-thick-cockInnocent-to-sluttyRoughDirty-TalkFuck-Me-Into-The-MatressCreampieImpregMultiple-Real-Orgasms"),
        ("chirb.it", "http://chirb.it/s80vbt"),
        ("eraudica", "https://www.eraudica.com/e/eve/2015/Twin-TLC-Dr-Eve-and-Nurse-Eve-a-Sucking-Fucking-Hospital-Romp"),
    ]

r_infos = [{
        "r_user": "test_user",
        "title": "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][incest][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Denial][Toys][Mast][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]",
        "selftext": "Testing selftext",
        "created_utc": "created_utc_sgasm",
        "r_post_url": "r_post_url_sgasm",
        "id": "id_sgasm",
        "permalink": "permalink_sgasm",
        "subreddit": "subreddit_sgasm"
    },
    {
        "r_user": "test_user",
        "title": "[FF4M] It's not what you think, brother! [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with /u/alwaysslightlysleepy]",
        "selftext": "Testing selftext",
        "created_utc": "created_utc_chirbit",
        "r_post_url": "r_post_url_chirbit",
        "id": "id_chirbit",
        "permalink": "permalink_chirbit",
        "subreddit": "subreddit_chirbit"
    },
    {
        "r_user": "test_user",
        "title": "[F4M] Nurse Eve and Dr. Eve Double Team TLC! [twins][binaural][medical][sucking and licking and fucking and cumming!][face sitting][riding your cock] [repost]",
        "selftext": "Testing selftext",
        "created_utc": "created_utc_eraudica",
        "r_post_url": "r_post_url_eraudica",
        "id": "id_eraudica",
        "permalink": "permalink_eraudica",
        "subreddit": "subreddit_eraudica"
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
    if a.filename_local:  # coming from download test not just info test
        os.remove(os.path.join(testdir, a.name_usr, a.filename_local))
        os.remove(os.path.join(testdir, a.name_usr, a.filename_local + ".txt"))
        os.rmdir(os.path.join(testdir, a.name_usr))
    del a


@pytest.fixture
def gen_audiodl_failed():
    a = AudioDownload("https://soundgasm.net/u/miyu213/F4M-Im-your-Pornstar-Cumdumpster-FAILED", "sgasm")
    a.url_to_file = "https://soundgasm.net/sounds/e764a6235fa9ca989721d97fc724dgdfg2d.m4a"
    a.title = "F4M-Im-your-Pornstar-Cumdumpster-FAILED"
    a.file_type = ".m4a"
    yield a, testdir
    os.rmdir(os.path.join(testdir, "miyu213"))


# @pytest.fixture
# def gen_audiodl_chirbit():
#     a = AudioDownload(urls[1][1], urls[1][0], r_infos[1])

#     yield a, testdir

#     if a.filename_local:  # coming from download test not just info test
#         os.remove(os.path.join(testdir, a.name_usr, a.filename_local))
#         os.remove(os.path.join(testdir, a.name_usr, a.filename_local + ".txt"))
#         os.rmdir(os.path.join(testdir, a.name_usr))
#     del a


@pytest.fixture
def gen_audiodl_eraudica(tmpdir):
    a = AudioDownload(urls[2][1], urls[2][0], r_infos[2])

    yield a, testdir

    if a.filename_local:  # coming from download test not just info test
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


def test_soundgasm_info(gen_audiodl_sgasm):
    a, dir = gen_audiodl_sgasm
    a.call_host_get_file_info()
    # all info is correct
    assert a.url_to_file == "https://soundgasm.net/sounds/e764a6235fa9ca5e23ee10b3989721d97fc7242d.m4a"
    assert a.file_type == ".m4a"
    assert a.title == "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]"
    assert a.descr == "Tribute to one of my listener, you know who you are, love <3"


@pytest.mark.dltest
def test_soundgasm(gen_audiodl_sgasm, create_db_download, create_new_test_con):
    con, c = create_db_download
    fn = "[F4M] I_m your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]"[0:110] + ".m4a"
    a, dir = gen_audiodl_sgasm
    a.call_host_get_file_info()

    # download worked
    a.download(con, 0, 0, dir)
    # fn gets gererated in dl method
    assert a.filename_local == fn
    assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert md5(os.path.join(dir, a.name_usr, fn)) == "60fec6dc98e1d16fb73fad2d31c50588"
    assert a.downloaded is True

    new_con, new_c = create_new_test_con  # testing if visible from other con
    id = c.lastrowid
    expected = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', None, 'TESTTITLE', 'testfile',
              'https://hostdomain.com/sub/TESTURL/', None, 'TESTPOSTURL', None, 'TESTREDDITTITLE', None,
              'TESTTEDDITUSER', 'TESTUSER', None), (
             2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0, None,
             'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR'),
            # not testing date time, using whatever the attributes are
             (3, a.date, a.time, 'Tribute to one of my listener, you know who you are, love <3', fn, "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]",
                "https://soundgasm.net/sounds/e764a6235fa9ca5e23ee10b3989721d97fc7242d.m4a", urls[0][1], "created_utc_sgasm", "r_post_url_sgasm", "id_sgasm",
              "[F4M] I'm your Pornstar Cumdumpster Slut Mother [Rape][Blackmail][incest][Facefucking][Slap my face with that thick cock][Innocent to slutty][Rough][Denial][Toys][Mast][Dirty Talk][Fuck Me Into The Matress][Creampie][Impreg][Multiple Real Orgasms]",
              "permalink_sgasm", 'test_user', 'miyu213', "subreddit_sgasm")
             ]
    new_c.execute("SELECT * FROM Downloads")
    assert new_c.fetchall() == expected

    # selftext written correctly
    with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
        assert f.read() == "Title: {}\nPermalink: {}\nSelftext:\n\n{}".format(a.reddit_info["title"],
                                                                               a.reddit_info["permalink"],
                                                                               a.reddit_info["selftext"])


# chirbit doesnt seem to be working anymore even in my browser
# def test_chirbit_info(gen_audiodl_chirbit):
#     a, dir = gen_audiodl_chirbit
#     a.call_host_get_file_info()
#     # only compare till aws id other part of url changes every time
#     assert a.url_to_file.split("&",1)[0] == "http://audio.chirbit.com/Pip_1446845763.mp3?AWSAccessKeyId=AKIAIHJD7T6NGQMM2VCA"
#     assert a.file_type == ".mp3"


# @pytest.mark.dltest
# def test_chirbit(gen_audiodl_chirbit, create_db_download, create_new_test_con):
#     con, c = create_db_download
#     fn = "[FF4M] It_s not what you think, brother_ [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with _u_alwaysslightlysleepy]"[0:110] + ".mp3"
#     a, dir = gen_audiodl_chirbit
#     a.call_host_get_file_info()

#     a.download(con, 0, 0, dir)
#     assert a.filename_local == fn
#     assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
#     assert md5(os.path.join(dir, a.name_usr, fn)) == "e8ff0e482d1837cd8be723c64b3ae32f"
#     assert a.downloaded is True

#     new_con, new_c = create_new_test_con  # testing if visible from other con
#     id = c.lastrowid
#     expected = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', None, 'TESTTITLE', 'testfile',
#                  'https://hostdomain.com/sub/TESTURL/', None, 'TESTPOSTURL', None, 'TESTREDDITTITLE', None,
#                  'TESTTEDDITUSER', 'TESTUSER', None), (
#                     2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0,
#                     None,
#                     'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR'),
#                 # not testing date time, using whatever the attributes are
#                 (3, a.date, a.time, None, fn,
#                  "[FF4M] It's not what you think, brother! [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with /u/alwaysslightlysleepy]",
#                  a.url_to_file, urls[1][1],
#                  "created_utc_chirbit", "r_post_url_chirbit", "id_chirbit",
#                  "[FF4M] It's not what you think, brother! [Age] [rape] [incest] [virginity] [impregnation] [vibrator] [reluctance] [lesbian sisters] [together with /u/alwaysslightlysleepy]",
#                  "permalink_chirbit", 'test_user', 'test_user', "subreddit_chirbit")
#                 ]
#     new_c.execute("SELECT * FROM Downloads")
#     assert new_c.fetchall() == expected

#     with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
#         assert f.read() == "Title: {}\nPermalink: {}\nSelftext:\n\n{}".format(a.reddit_info["title"],
#                                                                                a.reddit_info["permalink"],
#                                                                                a.reddit_info["selftext"])


def test_eraudica_info(gen_audiodl_eraudica):
    a, dir = gen_audiodl_eraudica
    a.call_host_get_file_info()
    assert a.url_to_file == "https://data1.eraudica.com/fd/71c71873-7356-4cee-bdfa-de1d0a652c3c_/Twins%20-%20Nurse%20Eve%20and%20Dr.%20Eve.mp3"
    assert a.file_type == ".mp3"


@pytest.mark.dltest
def test_eraudica(gen_audiodl_eraudica, create_db_download, create_new_test_con):
    con, c = create_db_download
    fn = "[F4M] Nurse Eve and Dr. Eve Double Team TLC_ [twins][binaural][medical][sucking and licking and fucking and cumming_][face sitting][riding your cock] [repost]"[0:110] + ".mp3"
    a, dir = gen_audiodl_eraudica
    a.call_host_get_file_info()
    assert a.url_to_file == "https://data1.eraudica.com/fd/71c71873-7356-4cee-bdfa-de1d0a652c3c_/Twins%20-%20Nurse%20Eve%20and%20Dr.%20Eve.mp3"
    assert a.file_type == ".mp3"

    a.download(con, 0, 0, dir)
    assert a.filename_local == fn
    assert os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert md5(os.path.join(dir, a.name_usr, fn)) == "b26ffe08e2068a822234a22aa7a7f40a"
    assert a.downloaded is True

    new_con, new_c = create_new_test_con  # testing if visible from other con
    id = c.lastrowid
    expected = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', None, 'TESTTITLE', 'testfile',
                 'https://hostdomain.com/sub/TESTURL/', None, 'TESTPOSTURL', None, 'TESTREDDITTITLE', None,
                 'TESTTEDDITUSER', 'TESTUSER', None), (
                    2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0,
                    None,
                    'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR'),
                # not testing date time, using whatever the attributes are
                (3, a.date, a.time, None, fn,
                 "[F4M] Nurse Eve and Dr. Eve Double Team TLC! [twins][binaural][medical][sucking and licking and fucking and cumming!][face sitting][riding your cock] [repost]",
                 "https://data1.eraudica.com/fd/71c71873-7356-4cee-bdfa-de1d0a652c3c_/Twins%20-%20Nurse%20Eve%20and%20Dr.%20Eve.mp3", urls[2][1],
                 "created_utc_eraudica", "r_post_url_eraudica", "id_eraudica",
                 "[F4M] Nurse Eve and Dr. Eve Double Team TLC! [twins][binaural][medical][sucking and licking and fucking and cumming!][face sitting][riding your cock] [repost]",
                 "permalink_eraudica", 'test_user', 'test_user', "subreddit_eraudica")
                ]
    new_c.execute("SELECT * FROM Downloads")
    assert new_c.fetchall() == expected

    with open(os.path.join(dir, a.name_usr, fn + ".txt"), "r") as f:
        assert f.read() == "Title: {}\nPermalink: {}\nSelftext:\n\n{}".format(a.reddit_info["title"],
                                                                               a.reddit_info["permalink"],
                                                                               a.reddit_info["selftext"])


def test_download_failed(gen_audiodl_failed, create_db_download, create_new_test_con):
    fn = "F4M-Im-your-Pornstar-Cumdumpster-FAILED.m4a"
    con, c = create_db_download
    a, dir = gen_audiodl_failed

    a.download(con, 0, 0, dir)
    assert not os.path.isfile(os.path.join(dir, a.name_usr, fn))
    assert a.downloaded is False

    new_con, new_c = create_new_test_con  # testing if visible from other con
    # testing if rollback happened on exception raised
    expected = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', None, 'TESTTITLE', 'testfile',
                 'https://hostdomain.com/sub/TESTURL/', None, 'TESTPOSTURL', None, 'TESTREDDITTITLE', None,
                 'TESTTEDDITUSER', 'TESTUSER', None), (
                    2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0,
                    None,
                    'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR')
                ]
    new_c.execute("SELECT * FROM Downloads")
    assert new_c.fetchall() == expected

    assert not os.path.isfile(os.path.join(dir, a.name_usr, fn + ".txt"))



@pytest.fixture
def create_new_test_con():
    conn = sqlite3.connect(os.path.join(testdir, "testdb.sqlite"))
    c = conn.cursor()
    yield conn, c
    conn.close()
    try:
        os.remove(os.path.join(testdir, "testdb.sqlite"))
    except PermissionError:
        pass


@pytest.fixture
def create_db_download():
    conn = sqlite3.connect(os.path.join(testdir, "testdb.sqlite"))
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT, "
              "description TEXT, local_filename TEXT, title TEXT, url_file TEXT, url TEXT, created_utc REAL, "
              "r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
              "sgasm_user TEXT, subreddit_name TEXT)")

    val_dict = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "TESTDESCR",
        "local_filename": None,
        "title": "TESTTITLE",
        "url_file": "testfile",
        "url": "https://hostdomain.com/sub/TESTURL/",
        "sgasm_user": "TESTUSER",
        "created_utc": None,
        "r_post_url": "TESTPOSTURL",
        "reddit_id": None,
        "reddit_title": "TESTREDDITTITLE",
        "reddit_url": None,
        "reddit_user": "TESTTEDDITUSER",
        "subreddit_name": None
    }

    val_dict2 = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "TESTDESCR",
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "testfile2",
        "url": None,
        "sgasm_user": "TESTUSER",
        "created_utc": 12345.0,
        "r_post_url": None,
        "reddit_id": "test6f78d",
        "reddit_title": None,
        "reddit_url": "TESTREDDITURL",
        "reddit_user": None,
        "subreddit_name": "TESTSUBR"
    }

    c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                           "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                           "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                           ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                           ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                           ":sgasm_user, :subreddit_name)", val_dict)

    c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
              "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
              "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
              ":description, :local_filename, :title, :url_file, :url, :created_utc, "
              ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
              ":sgasm_user, :subreddit_name)", val_dict2)
    # commit changes
    conn.commit()

    yield conn, c

    conn.close()
    try:
        os.remove(os.path.join(testdir, "testdb.sqlite"))
    except PermissionError:
        print("!!!!!!!!!!TEST DB FILE HASNT BEEN DELETED!!!!!!!!")


@pytest.fixture
def create_db_missing():
    conn = sqlite3.connect(os.path.join(testdir, "testdb.sqlite"))
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT, "
              "description TEXT, local_filename TEXT, title TEXT, url_file TEXT, url TEXT, created_utc REAL, "
              "r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
              "sgasm_user TEXT, subreddit_name TEXT)")

    val_dict = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "TESTDESCR",
        "local_filename": None,
        "title": "TESTTITLE",
        "url_file": "testfile",
        "url": "https://soundsm.net/u/TESTNOTREPL",
        "sgasm_user": "TESTUSER",
        "created_utc": None,
        "r_post_url": "TESTPOSTURL",
        "reddit_id": None,
        "reddit_title": "TESTREDDITTITLE",
        "reddit_url": None,
        "reddit_user": "TESTTEDDITUSER",
        "subreddit_name": None
    }

    val_dict2 = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "TESTDESCR",
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "testfile2",
        "url": None,
        "sgasm_user": "TESTUSER",
        "created_utc": 12345.0,
        "r_post_url": None,
        "reddit_id": "test6f78d",
        "reddit_title": None,
        "reddit_url": "TESTREDDITURL",
        "reddit_user": None,
        "subreddit_name": "TESTSUBR"
    }

    val_dict3 = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "TESTDESCR",
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "testfile3",
        "url": "https://soundsm.net/u/testu3/testfile3",
        "sgasm_user": "TESTUSER",
        "created_utc": 12345.0,
        "r_post_url": None,
        "reddit_id": "test6a48d",
        "reddit_title": None,
        "reddit_url": "TESTREDDITURL",
        "reddit_user": None,
        "subreddit_name": "TESTSUBR"
    }

    for vdict in (val_dict, val_dict2, val_dict3):
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                           "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                           "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                           ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                           ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                           ":sgasm_user, :subreddit_name)", vdict)
    # commit changes
    conn.commit()

    yield conn, c

    conn.close()
    try:
        os.remove(os.path.join(testdir, "testdb.sqlite"))
    except PermissionError:
        print("!!!!!!!!!!TEST DB FILE HASNT BEEN DELETED!!!!!!!!")


@pytest.fixture
def create_adl_missing():
    reddit_info = {"title": "testtitle", "permalink": "testperm",
                   "selftext": "testself", "r_user": "testruser",
                   "created_utc": 12345.0, "id": "test123",
                   "subreddit": "testsub", "r_post_url": "testpurl"}
    reddit_info2 = {"title": "testtitle2", "permalink": "testperm2",
                    "selftext": "testself2", "r_user": "testruser2",
                    "created_utc": 123456.0, "id": "test1232",
                    "subreddit": "testsub2", "r_post_url": "testpurl2"}
    reddit_info3 = {"title": "testtitle3", "permalink": "testperm3",
                    "selftext": "testself3", "r_user": "testruser3",
                    "created_utc": 1234567.0, "id": "test1233",
                    "subreddit": "testsub3", "r_post_url": "testpurl3"}

    adl = AudioDownload("https://soundsm.net/u/testu1/test1", "sgasm", reddit_info=reddit_info)
    adl.url_to_file = "testfile"
    adl.downloaded = True
    adl.title = "testtit"
    adl.filename_local = "testfn"
    adl.descr = "testdescr"
    adl.date = "testd"
    adl.time = "testt"

    adl2 = AudioDownload("https://soundgasm.net/u/testu2/test2", "sgasm", reddit_info=reddit_info2)
    adl2.url_to_file = "testfile2"
    adl2.downloaded = True
    adl2.title = "testtit2"
    adl2.filename_local = "testfn2"
    adl2.descr = "testdescr2"
    adl2.date = "testd2"
    adl2.time = "testt2"

    adl3 = AudioDownload("https://soundsm.net/u/testu3/testfile3", "sgasm", reddit_info=reddit_info3)
    adl3.url_to_file = "testfile3"
    adl3.downloaded = True
    adl3.title = "testtit3"
    adl3.filename_local = "testfn3"
    adl3.descr = "testdescr3"
    adl3.date = "testd3"
    adl3.time = "testt3"
    return adl, adl2, adl3


def test_set_missing_vals(create_db_missing, create_adl_missing):
    con, c = create_db_missing
    adl, adl2, adl3 = create_adl_missing

    start = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', None, 'TESTTITLE', 'testfile', 'https://soundsm.net/u/TESTNOTREPL', None, 'TESTPOSTURL', None, 'TESTREDDITTITLE', None, 'TESTTEDDITUSER', 'TESTUSER', None),
             (2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0, None, 'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR'),
             (3, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile3', 'https://soundsm.net/u/testu3/testfile3', 12345.0, None, 'test6a48d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR')]

    fill_one = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', "testfn", 'TESTTITLE', 'testfile', 'https://soundsm.net/u/TESTNOTREPL', 12345.0, 'TESTPOSTURL', "test123", 'TESTREDDITTITLE', "testperm", 'TESTTEDDITUSER', 'TESTUSER', "testsub"),
                (2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', None, 12345.0, None, 'test6f78d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR'),
                (3, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile3', 'https://soundsm.net/u/testu3/testfile3', 12345.0, None, 'test6a48d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR')]
    fill_two = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', "testfn", 'TESTTITLE', 'testfile', 'https://soundsm.net/u/TESTNOTREPL', 12345.0, 'TESTPOSTURL', "test123", 'TESTREDDITTITLE', "testperm", 'TESTTEDDITUSER', 'TESTUSER', "testsub"),
                (2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', "https://soundgasm.net/u/testu2/test2", 12345.0, "testpurl2", 'test6f78d', "testtitle2", 'TESTREDDITURL', "testruser2", 'TESTUSER', 'TESTSUBR'),
                (3, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile3', 'https://soundsm.net/u/testu3/testfile3', 12345.0, None, 'test6a48d', None, 'TESTREDDITURL', None, 'TESTUSER', 'TESTSUBR')]
    fill_three = [(1, 'TESTDATE', 'TESTIME', 'TESTDESCR', "testfn", 'TESTTITLE', 'testfile', 'https://soundsm.net/u/TESTNOTREPL', 12345.0, 'TESTPOSTURL', "test123", 'TESTREDDITTITLE', "testperm", 'TESTTEDDITUSER', 'TESTUSER', "testsub"),
                  (2, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile2', "https://soundgasm.net/u/testu2/test2", 12345.0, "testpurl2", 'test6f78d', "testtitle2", 'TESTREDDITURL', "testruser2", 'TESTUSER', 'TESTSUBR'),
                  (3, 'TESTDATE', 'TESTIME', 'TESTDESCR', 'TESTFILENAME', 'TESTTITLE', 'testfile3', 'https://soundsm.net/u/testu3/testfile3', 12345.0, "testpurl3", 'test6a48d', "testtitle3", 'TESTREDDITURL', "testruser3", 'TESTUSER', 'TESTSUBR')]
    c.execute("SELECT * FROM Downloads")
    result = c.fetchall()
    assert result == start
    # test returned filename
    assert adl.set_missing_values_db(con, url_type="file") is None
    c.execute("SELECT * FROM Downloads")
    result = c.fetchall()
    assert result == fill_one
    assert adl2.set_missing_values_db(con, url_type="file") == 'TESTFILENAME'
    c.execute("SELECT * FROM Downloads")
    result = c.fetchall()
    assert result == fill_two
    assert adl3.set_missing_values_db(con) == 'TESTFILENAME'
    c.execute("SELECT * FROM Downloads")
    result = c.fetchall()
    assert result == fill_three

@pytest.mark.parametrize("title, expected", [
    ("file_dled_but_no_url", None),
    ("[same]_file-name:but\\new_dl", "[same]_file-name_but_new_dl_01.txt"),
    ("[F4M] This, gonna.be good!! Gimme $$", "[F4M] This, gonna.be good__ Gimme __.txt"),
    # TODO also replace äüö?
    ("[F4M] This gonna be good [fun!] [not so äüö'#*?}]", "[F4M] This gonna be good [fun_] [not so äüö_____].txt"),
])
def test_gen_fn(title, expected, create_db_missing): # [^\w\-_.,\[\] ]
    adl = AudioDownload("https://soundgasm.net/u/testu1/blabla", "sgasm")
    adl.title = title
    adl.file_type = ".txt"
    if title == "file_dled_but_no_url":
        adl.url_to_file = "testfile"
    con, c = create_db_missing

    assert adl.gen_filename(con, testdir) == expected

@pytest.mark.parametrize("host, url, r_inf", [
    ("sgasm", "file:///N:/_archive/test/trans/soundgasmNET/_dev/_sgasm-repo/tests/test_dl/u/exc_dl/soundgasm.net.html",
     {"r_user": None}),
    ("chirb.it", "file:///N:/_archive/test/trans/soundgasmNET/_dev/_sgasm-repo/tests/test_dl/u/exc_dl/Chirbit.html",
     {"r_user": None}),
    ("eraudica", "file:///N:/_archive/test/trans/soundgasmNET/_dev/_sgasm-repo/tests/test_dl/u/exc_dl/Eraudica.html",
     {"r_user": None})
])
def test_info_extract_exc(host, url, r_inf):
    a = AudioDownload(url, host, r_inf)
    with pytest.raises(InfoExtractingError):
        a.call_host_get_file_info()
