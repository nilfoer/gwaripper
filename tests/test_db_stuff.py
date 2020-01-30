import pytest  # for fixture otherwise not needed
import sqlite3
import os
import csv
import time
import utils  # needed for valid logging dir hack
from gwaripper.audio_dl import AudioDownload, check_direct_url_for_dl
from gwaripper.gwaripper import filter_alrdy_downloaded
from gwaripper.db import export_csv_from_sql, backup_db
from gwaripper.config import config, write_config_module

time_str = time.strftime("%Y-%m-%d")
testdir = os.path.normpath("tests\\test_res")

@pytest.fixture
def create_dl_dict():
    reddit_info = {"title": "testtitle", "permalink": "testperm",
                   "selftext": "testself", "r_user": "testruser",
                   "created_utc": 12345.0, "id": "test123",
                   "subreddit": "testsub", "r_post_url": "testpurl"}
    reddit_info2 = {"title": "testtitle2", "permalink": "testperm2",
                    "selftext": "testself2", "r_user": "testruser2",
                    "created_utc": 123456.0, "id": "test1232",
                    "subreddit": "testsub2", "r_post_url": "testpurl2"}

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
    dl_dict = {"https://soundsm.net/u/testu1/test1": adl,
               "https://soundsm.net/u/testu2/test2": adl2}
    return dl_dict


@pytest.fixture
def create_db():
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
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "https://hostdomain.com/sub/TESTURL/TESTURLFILE.mp3",
        "url": "https://hostdomain.com/sub/TESTURL/",
        "sgasm_user": "TESTUSER",
        "created_utc": None,
        "r_post_url": None,
        "reddit_id": None,
        "reddit_title": None,
        "reddit_url": None,
        "reddit_user": None,
        "subreddit_name": None
    }

    for i in range(6):
        val_dict.update(url_file= "https://hostdomain.com/sub/TESTURL/TESTURLFILE{}.mp3".format(i))
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                           "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                           "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                           ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                           ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                           ":sgasm_user, :subreddit_name)", val_dict)
    # commit changes
    conn.commit()

    yield conn, c

    conn.close()
    os.remove(os.path.join(testdir, "testdb.sqlite"))


@pytest.fixture
def create_db_for_export():
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
        "description": "Mutli-line\nDescription, also containing\r\nCarriag returns\r\nTEST",
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "https://hostdomain.com/sub/TESTURL/TESTURLFILE.mp3",
        "url": "https://hostdomain.com/sub/TESTURL/",
        "sgasm_user": "TESTUSER",
        "created_utc": None,
        "r_post_url": None,
        "reddit_id": None,
        "reddit_title": None,
        "reddit_url": None,
        "reddit_user": None,
        "subreddit_name": None
    }

    for i in range(2):
        val_dict.update(url_file= "https://hostdomain.com/sub/TESTURL/TESTURLFILE{}.mp3".format(i))
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                           "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                           "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                           ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                           ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                           ":sgasm_user, :subreddit_name)", val_dict)
    # commit changes
    conn.commit()

    yield conn, c

    conn.close()
    os.remove(os.path.join(testdir, "testdb.sqlite"))
    os.remove(os.path.join(testdir, "export_test.csv"))


@pytest.mark.parametrize("url, expected", [
    ("https://hostdomain.com/sub/TESTURL/TESTURLFILE0.mp3", True),
    ("https://hostdomain.com/sub/TESTURL/TESTURLFILE3.mp3", True),
    ("https://hostdomain.com/sub/TESTURL/TESTURLFILE4.mp3", True),
    ("https://hostdomain.com/sub/TESTURL/TESTURLdgdgdgdg.mp3", False),
])
def test_check_dir_file_url(url, expected, create_db):
    con, c = create_db
    c.execute("SELECT * FROM Downloads")
    te=c.fetchall()
    assert check_direct_url_for_dl(con, url) is expected


def test_filter_dl(create_dl_dict, monkeypatch):
    dl_dict = create_dl_dict
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE Downloads(url);
        INSERT INTO Downloads(url) VALUES
            ('https://soundsm.net/u/testu1/test1'),
            ("https://soundsm.net/u/testu3/test3old"),
            ("https://soundsm.net/u/testu4/test4old");""")

    filtered = filter_alrdy_downloaded(dl_dict, con)
    assert filtered == {"https://soundsm.net/u/testu2/test2"}


@pytest.fixture
def create_db_for_bu():
    config["Settings"]["max_db_bu"] = "5"
    sql_path = os.path.join(testdir, "testdb.sqlite")
    csv_path = os.path.join(testdir, "export_test.csv")

    conn = sqlite3.connect(sql_path)
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT, "
              "description TEXT, local_filename TEXT, title TEXT, url_file TEXT, url TEXT, created_utc REAL, "
              "r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
              "sgasm_user TEXT, subreddit_name TEXT)")

    val_dict = {
        "date": "TESTDATE",
        "time": "TESTIME",
        "description": "Mutli-line\nDescription, also containing\r\nCarriag returns\r\nTEST",
        "local_filename": "TESTFILENAME",
        "title": "TESTTITLE",
        "url_file": "https://hostdomain.com/sub/TESTURL/TESTURLFILE.mp3",
        "url": "https://hostdomain.com/sub/TESTURL/",
        "sgasm_user": "TESTUSER",
        "created_utc": None,
        "r_post_url": None,
        "reddit_id": None,
        "reddit_title": None,
        "reddit_url": None,
        "reddit_user": None,
        "subreddit_name": None
    }

    for i in range(2):
        val_dict.update(url_file= "https://hostdomain.com/sub/TESTURL/TESTURLFILE{}.mp3".format(i))
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                           "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                           "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                           ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                           ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                           ":sgasm_user, :subreddit_name)", val_dict)
    # commit changes
    conn.commit()

    export_csv_from_sql(csv_path, conn)

    yield conn, c, sql_path, csv_path

    conn.close()
    os.remove(sql_path)
    os.remove(csv_path)


    files_in_bu = os.listdir(os.path.join(testdir, "_db-autobu"))
    while files_in_bu:
        os.remove(os.path.join(testdir, "_db-autobu", files_in_bu.pop()))
    os.rmdir(os.path.join(testdir, "_db-autobu"))

    config["Settings"]["db_bu_freq"] = "4.5"
    config["Time"]["last_db_bu"] = "0.0"
    write_config_module()



def md5(fname):
    import hashlib
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


def test_export_csv(create_db_for_export):
    expected = [['id','date', 'time', 'description', 'local_filename', 'title', 'url_file', 'url', 'created_utc',
                 'r_post_url','reddit_id', 'reddit_title', 'reddit_url', 'reddit_user', 'sgasm_user', 'subreddit_name'],
                ["1", "TESTDATE", "TESTIME", "Mutli-line\nDescription, also containing\r\nCarriag returns\r\nTEST",
                 "TESTFILENAME","TESTTITLE", "https://hostdomain.com/sub/TESTURL/TESTURLFILE0.mp3",
                 "https://hostdomain.com/sub/TESTURL/", "", "", "", "", "", "", "TESTUSER", ""],
                ["2", "TESTDATE", "TESTIME", "Mutli-line\nDescription, also containing\r\nCarriag returns\r\nTEST",
                 "TESTFILENAME", "TESTTITLE", "https://hostdomain.com/sub/TESTURL/TESTURLFILE1.mp3",
                 "https://hostdomain.com/sub/TESTURL/", "", "", "", "", "", "", "TESTUSER", ""]]

    con, c = create_db_for_export
    export_csv_from_sql(os.path.join(testdir, "export_test.csv"), con)
    rows = []
    with open(os.path.join(testdir, "export_test.csv"), "r", newline="", encoding='utf-8') as csvf:
        csv_reader = csv.reader(csvf, dialect="excel", delimiter=';')
        for row in csv_reader:
            rows.append(row)
    assert rows == expected


@pytest.mark.parametrize("last_bu, bu_freq, csv_bu, force, backuped, too_many", [
    ("0.0", "5", False, False, True, False),  # def bu no csv
    ("0.0", "5", False, False, True, True),  # def bu, too many bus in budir no csv
    ("0.0", "5", True, False, True, True),  # def bu, too many bus in budir + csv
    (str(time.time()), "5", False, False, False, False),  # now -> no bu
    (str(time.time()), "5", False, True, True, False),  # now but force bu no csv
    (str(time.time()), "5", True, True, True, False),  # now but force bu + csv
    (str(time.time()-(5.5*24*60*60)), "5", False, False, True, False),  # last bu 5.5 days ago -> bu
    (str(time.time()-(5.5*24*60*60)), "5", True, False, True, False),  # last bu 5.5 days ago -> bu + csv
    (str(time.time() - (10.5 * 24 * 60 * 60)), "10", True, False, True, False)  # last bu 10.5 days ago -> bu + csv
])
def test_backup_db(last_bu, bu_freq, csv_bu, force, backuped, too_many, create_db_for_bu):
    bu_dir = os.path.join(testdir, "_db-autobu")
    bu_sql_path = os.path.join(bu_dir, "{}_gwarip_db.sqlite".format(time_str))
    bu_csv_path = os.path.join(bu_dir, "{}_gwarip_db_exp.csv".format(time_str))

    config["Settings"]["db_bu_freq"] = bu_freq
    config["Time"]["last_db_bu"] = last_bu

    # create files
    if too_many:
        if not os.path.exists(bu_dir):
            os.makedirs(bu_dir)
        for i in range(5):
            with open(os.path.join(bu_dir, "{}.sqlite".format(i)), "w") as w:
                w.write("")

        with open(os.path.join(bu_dir, "0_exp.csv"), "w") as w:
            w.write("")


    con, c, sql_p, csv_p = create_db_for_bu

    if csv_bu:
        backup_db(sql_p, csv_p, force, bu_dir)
    else:
        backup_db(sql_p, None, force, bu_dir)

    if backuped:
        assert md5(bu_sql_path) == md5(sql_p)
        if csv_bu:
            assert md5(bu_csv_path) == md5(csv_p)
        else:
            assert not os.path.isfile(bu_csv_path)
    else:
        assert not os.path.isfile(bu_sql_path)
        assert not os.path.isfile(bu_csv_path)

    if too_many:
        # deleted one bu if too_many, also deleted csv if written
        assert len([f for f in os.listdir(bu_dir) if f.endswith(".sqlite")]) <= 5
        assert not os.path.isfile(os.path.join(bu_dir, "0_exp.csv"))

