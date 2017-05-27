import pytest  # for fixture otherwise not needed
import sqlite3
import os
from gwaripper.gwaripper import AudioDownload, filter_alrdy_downloaded, check_direct_url_for_dl

testdir = os.path.normpath("N:\\_archive\\test\\trans\soundgasmNET\\_dev\\_sgasm-repo\\tests\\test_res")

@pytest.fixture
def create_dl_dict():
    # import pandas as pd
    # df_dummy = pd.DataFrame(
    #     data=[['Date', 'Description: DummyLine', 'Local_filename', 'Time', 'Title: DummyTitle', 'URL',
    #            'URLsg', 'redditURL', 'sgasm_user', 'reddit_user', 0, 'redditTitle',
    #            1234.0, 'redditID', 'subredditName', 'rPostUrl']],
    #     columns=['Date', 'Description', 'Local_filename', 'Time', 'Title', 'URL',
    #              'URLsg', 'redditURL', 'sgasm_user', 'reddit_user', 'filenr', 'redditTitle',
    #              'created_utc', 'redditID', 'subredditName', 'rPostUrl'])
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
        "created_utc": "NULL",
        "r_post_url": "NULL",
        "reddit_id": "NULL",
        "reddit_title": "NULL",
        "reddit_url": "NULL",
        "reddit_user": "NULL",
        "subreddit_name": "NULL"
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


# def create_df_append():
#     import pandas as pd
#     from numpy import nan
#
#     df_dummy, dl_dict = create_df_dl_dict()
#
#     # manually created df to match
#     df_appended = pd.DataFrame(
#         data=[['Date', 'Description: DummyLine', 'Local_filename', 'Time', 'Title: DummyTitle', 'URL',
#                'URLsg', 1234.0, 0, 'rPostUrl', 'redditID', 'redditTitle', 'redditURL', 'reddit_user', 'sgasm_user',
#                'subredditName'],
#               ['testd', 'testdescr', 'testfn', 'testt', 'testtit', 'testfile',
#                'https://soundsm.net/u/testu1/test1', 12345.0, nan, 'testpurl', 'test123', 'testtitle',
#                'testperm', 'testruser', 'testu1', 'testsub'],
#               ['testd2', 'testdescr2', 'testfn2', 'testt2', 'testtit2', 'testfile2',
#                'https://soundgasm.net/u/testu2/test2', 123456.0, nan, 'testpurl2', 'test1232', 'testtitle2',
#                'testperm2', 'testruser2', 'testu2', 'testsub2']],
#         columns=['Date', 'Description', 'Local_filename', 'Time', 'Title', 'URL',
#                  'URLsg', 'created_utc', 'filenr', 'rPostUrl', 'redditID', 'redditTitle',
#                  'redditURL', 'reddit_user', 'sgasm_user','subredditName'])
#
#     new_dls = ["https://soundsm.net/u/testu1/test1", "https://soundgasm.net/u/testu2/test2"]
#
#     # also use append to create df to match
#     # df_append_dict = {"Date": ["testd", "testd2"], "Time": ["testt", "testt2"], "Local_filename": ["testfn", "testfn2"],
#     #                   "Description": ["testdescr", "testdescr2"], "Title": ["testtit", "testtit2"], "URL": ["testfile", "testfile2"],
#     #                   "URLsg": ["https://soundsm.net/u/testu1/test1", "https://soundgasm.net/u/testu2/test2"],
#     #                   "sgasm_user": ["testu1", "testu2"], "redditURL": ["testperm", "testperm2"],
#     #                   "reddit_user": ["testruser", "testruser2"], "redditTitle": ["testtitle", "testtitle2"],
#     #                   "created_utc": [12345.0, 123456.0], "redditID": ["test123", "test1232"],
#     #                   "subredditName": ["testsub", "testsub2"], "rPostUrl": ["testpurl", "testpurl2"]}
#     #
#     # df_dict = pd.DataFrame.from_dict(df_append_dict)
#     # df_appended = df_dummy.append(df_dict, ignore_index=True, verify_integrity=True)
#
#     return df_dummy, new_dls, dl_dict, df_appended


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


def test_filter_dl(create_dl_dict):
    dled = {"https://soundsm.net/u/testu1/test1",
            "https://soundsm.net/u/testu3/test3old", "https://soundsm.net/u/testu4/test4old"}
    dl_dict = create_dl_dict
    filtered = filter_alrdy_downloaded(dled, dl_dict, 0)
    assert filtered == {"https://soundsm.net/u/testu2/test2"}

