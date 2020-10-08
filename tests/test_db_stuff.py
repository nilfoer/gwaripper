import pytest  # for fixture otherwise not needed
import sqlite3
import os
import csv
import time

# needed for valid logging dir hack
from utils import gen_hash_from_file, setup_tmpdir, TESTS_DIR

from gwaripper.db import export_csv_from_sql, backup_db
from gwaripper.config import config, write_config_module

time_str = time.strftime("%Y-%m-%d")
TEST_FILES_DIR = os.path.join(TESTS_DIR, "test_res")


@pytest.fixture
def create_db_for_export(setup_tmpdir):
    conn = sqlite3.connect(os.path.join(setup_tmpdir, "testdb.sqlite"))
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, "
              "date TEXT, time TEXT, description TEXT, local_filename TEXT, title TEXT, "
              "url_file TEXT, url TEXT, created_utc REAL, r_post_url TEXT, reddit_id TEXT,"
              "reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
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
        val_dict.update(url_file="https://hostdomain.com/sub/TESTURL/TESTURLFILE{}.mp3".format(i))
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                  "title, url_file, url, created_utc, r_post_url, reddit_id, "
                  "reddit_title, reddit_url, reddit_user, sgasm_user, "
                  "subreddit_name) VALUES (:date, :time, :description, "
                  ":local_filename, :title, :url_file, :url, :created_utc, "
                  ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                  ":sgasm_user, :subreddit_name)", val_dict)
    # commit changes
    conn.commit()

    yield setup_tmpdir, conn, c

    # setup_tmpdir takes care of deleting files
    conn.close()


@pytest.fixture
def create_db_for_bu(setup_tmpdir):
    config["Settings"]["max_db_bu"] = "5"
    sql_path = os.path.join(setup_tmpdir, "testdb.sqlite")
    csv_path = os.path.join(setup_tmpdir, "export_test.csv")

    conn = sqlite3.connect(sql_path)
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, "
              "date TEXT, time TEXT, description TEXT, local_filename TEXT, title "
              "TEXT, url_file TEXT, url TEXT, created_utc REAL, r_post_url TEXT, "
              "reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
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
        val_dict.update(url_file="https://hostdomain.com/sub/TESTURL/TESTURLFILE{}.mp3".format(i))
        c.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                  "title, url_file, url, created_utc, r_post_url, reddit_id,"
                  " reddit_title, reddit_url, reddit_user, sgasm_user, "
                  "subreddit_name) VALUES (:date, :time, :description, "
                  ":local_filename, :title, :url_file, :url, :created_utc, "
                  ":r_post_url, :reddit_id, :reddit_title, :reddit_url, "
                  ":reddit_user, :sgasm_user, :subreddit_name)", val_dict)
    # commit changes
    conn.commit()

    export_csv_from_sql(csv_path, conn)

    yield setup_tmpdir, conn, c, sql_path, csv_path

    conn.close()

    config["Settings"]["db_bu_freq"] = "4.5"
    config["Time"]["last_db_bu"] = "0.0"
    write_config_module()


def test_export_csv(create_db_for_export):
    expected = [['id', 'date', 'time', 'description', 'local_filename', 'title',
                 'url_file', 'url', 'created_utc', 'r_post_url', 'reddit_id',
                 'reddit_title', 'reddit_url', 'reddit_user', 'sgasm_user', 'subreddit_name'],
                ["1", "TESTDATE", "TESTIME", "Mutli-line\nDescription, also containing\r\n"
                 "Carriag returns\r\nTEST", "TESTFILENAME", "TESTTITLE",
                 "https://hostdomain.com/sub/TESTURL/TESTURLFILE0.mp3",
                 "https://hostdomain.com/sub/TESTURL/", "", "", "", "", "", "", "TESTUSER", ""],
                ["2", "TESTDATE", "TESTIME", "Mutli-line\nDescription, also containing"
                 "\r\nCarriag returns\r\nTEST", "TESTFILENAME", "TESTTITLE",
                 "https://hostdomain.com/sub/TESTURL/TESTURLFILE1.mp3",
                 "https://hostdomain.com/sub/TESTURL/", "", "", "", "", "", "", "TESTUSER", ""]]

    tmpdir, con, c = create_db_for_export
    export_csv_from_sql(os.path.join(tmpdir, "export_test.csv"), con)
    rows = []
    with open(os.path.join(tmpdir, "export_test.csv"),
              "r", newline="", encoding='utf-8') as csvf:
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
    # last bu 5.5 days ago -> bu
    (str(time.time()-(5.5*24*60*60)), "5", False, False, True, False),
    # last bu 5.5 days ago -> bu + csv
    (str(time.time()-(5.5*24*60*60)), "5", True, False, True, False),
    # last bu 10.5 days ago -> bu + csv
    (str(time.time() - (10.5 * 24 * 60 * 60)), "10", True, False, True, False)
])
def test_backup_db(last_bu, bu_freq, csv_bu, force, backuped, too_many, create_db_for_bu):
    tmpdir, con, c, sql_p, csv_p = create_db_for_bu
    bu_dir = os.path.join(tmpdir, "_db-autobu")
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

    if csv_bu:
        backup_db(sql_p, csv_p, force, bu_dir)
    else:
        backup_db(sql_p, None, force, bu_dir)

    if backuped:
        assert gen_hash_from_file(bu_sql_path, 'md5', _hex=True) == gen_hash_from_file(
                sql_p, 'md5', _hex=True)
        if csv_bu:
            assert gen_hash_from_file(bu_csv_path, 'md5', _hex=True) == gen_hash_from_file(
                    csv_p, 'md5', _hex=True)
        else:
            assert not os.path.isfile(bu_csv_path)
    else:
        assert not os.path.isfile(bu_sql_path)
        assert not os.path.isfile(bu_csv_path)

    if too_many:
        # deleted one bu if too_many, also deleted csv if written
        assert len([f for f in os.listdir(bu_dir) if f.endswith(".sqlite")]) <= 5
        assert not os.path.isfile(os.path.join(bu_dir, "0_exp.csv"))
