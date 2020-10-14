import pytest
import os
import time
import sqlite3

import gwaripper.config as cfg

from gwaripper.gwaripper import GWARipper
from gwaripper.db import load_or_create_sql_db
from gwaripper.info import FileInfo, RedditInfo, FileCollection
from gwaripper.exceptions import InfoExtractingError
from utils import build_test_dir_furl, TESTS_DIR, setup_tmpdir

# TODO to test:
#
# download_file/collection + mb download_in_chunks
#
# test advanced db.py procedures (search_sytnax_parser, etc.)? they're taken from my other project

TESTS_FILES_DIR = os.path.join(TESTS_DIR, "test_dl")


def test_set_missing_reddit(setup_tmpdir):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir

    test_db = os.path.join(tmpdir, "gwarip_db.sqlite")
    test_con, test_c = load_or_create_sql_db(test_db)

    test_c.executescript("""
    BEGIN TRANSACTION;

    INSERT INTO Downloads(
        date, time, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user,
        subreddit_name
        )
    VALUES
        ("2020-01-23", "13:37", "This is a description", "audio_file.m4a",
         "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
         "https://soundgasm.net/sassmastah77/Audio-title-ASMR", NULL,
         NULL, NULL, NULL, NULL, NULL, "sassmastah77", NULL),

        ("2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
         "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
         "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
         "26iw32o", NULL, NULL, NULL, "testy_user", NULL),

        ("2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", NULL,
         "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate elongate elongate elongate elongate elongate elongate",
         "https://no-page-url.com/324q523q.mp3", NULL, 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
         "2klj654", "don_t change this", NULL, NULL, "old_user", NULL);

    COMMIT;
    """)

    test_con.close()

    fi = FileInfo(object, True, "m4a", "https://soundgasm.net/sassmastah77/Audio-title-ASMR",
                  "https://soundgasm.net/284291412sa324.m4a", None,
                  "AudiLEAVE_PRESENT_FIELDS_UNCHANGED [ASMR]",
                  "ThisLEAVE_PRESENT_FIELDS_UNCHANGEDion", "LEAVE_PRESENT_FIELDS_UNCHANGED77")
    ri = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                    "inserted_reddit_id", "isnerted_reddit_title", "inserted-reddit-user",
                    "inserted/subreddit", [fi])
    ri.permalink = "inserted_rddt_url"
    ri.selftext = None
    ri.created_utc = 1254323.0
    ri.subreddit = "ssssubreddit"
    ri.r_post_url = "url-to-self-or-outgoing"

    # nothing should happen
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    expected = [
            [1, "2020-01-23", "13:37", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", None, None, None],
            [2, "2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", None, None, None],
            [3, "2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", None, None, None],
            ]

    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()

    assert rows == [tuple(r) for r in expected]

    fi.parent = ri
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    expected[0][8:16] = [1254323.0, ri.r_post_url, ri.id, ri.title, ri.permalink,
                         ri.author, "sassmastah77", ri.subreddit]
    # selftext not written
    assert os.listdir(tmpdir) == ['gwarip_db.sqlite', 'gwarip_db_exp.csv', '_db-autobu']

    # reconnect so we make sure it's visible from diff connections
    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()
    assert rows == [tuple(r) for r in expected]

    ri.selftext = "selffffffftext"
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    # selftext written
    with open(os.path.join(tmpdir, "sassmastah77", "audio_file.m4a.txt"), 'r') as f:
        assert f.read() == ("Title: isnerted_reddit_title\nPermalink: inserted_rddt_url\n"
                            "Selftext:\n\nselffffffftext")

    # unchanged rows
    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()
    assert rows == [tuple(r) for r in expected]

    # garbage fields for already present col so we can check that they don't get changed
    fi = FileInfo(object, True, "m4a", "https://soundgasm.net/testy_user/Best-title-SFW",
                  "https://soundgasm.net/24634adra354.m4a", None,
                  "BeLEAVE_PRESENT_FIELDS_UNCHANGEDe [SFW]",
                  "This iLEAVE_PRESENT_FIELDS_UNCHANGEDscription",
                  "LEAVE_PRESENT_FIELDS_UNCHANGED_user")
    ri = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                    "LEAVE_PRESENT_FIELDS_UNCHANGED", "isnerte222d_reddit_title",
                    "inserted-reddit-user", "inserted/subreddit", [fi])
    ri.permalink = "inserted_rddt2_url"
    ri.selftext = "selfff2fffftext"
    ri.created_utc = 11111111.0
    ri.r_post_url = "LEAVE_PRESENT_FIELDS_UNCHANGED"
    fi.parent = ri

    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    expected[1][8:16] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                         "26iw32o", ri.title, ri.permalink, ri.author,
                         "testy_user", ri.subreddit]

    # selftext written
    with open(os.path.join(tmpdir, "testy_user", "subpath", "super_file.mp3.txt"), 'r') as f:
        assert f.read() == ("Title: isnerte222d_reddit_title\nPermalink: inserted_rddt2_url\n"
                            "Selftext:\n\nselfff2fffftext")

    # reconnect so we make sure it's visible from diff connections
    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()
    assert rows == [tuple(r) for r in expected]

    fi = FileInfo(object, True, "m4a", "insertedPAGEURL",
                  "https://no-page-url.com/324q523q.mp3", None,
                  "Use title from DB!",  # needed for selftext fn
                  "This iLEAgsgVE_PRESENT_FIELDS_UNCHANGEDscription",
                  "LEAVE_PRESENT_sgsFIELDS_UNCHANGED_user")
    ri = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                    "LEAVE_PRESENT_FIELDS_UNCHANGED", "LEAVE_TITLE_FIELD_UNCHANGED",
                    "inserted-reddit3-user", "inserted3/subreddit", [fi])
    ri.permalink = "inserted_rddt3_url"
    ri.selftext = "selfff3fffdszlbdftext"
    ri.created_utc = 111111.0
    ri.r_post_url = "LEAVE_PRESENT_FIELDS_UNCHANGED"
    fi.parent = ri

    # no page url in db
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi, use_file_url=True)

    # page url inserted
    expected[2][7] = "insertedPAGEURL"
    expected[2][8:16] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
                         "2klj654", "don_t change this", ri.permalink, ri.author,
                         "old_user", ri.subreddit]

    fn = ("No-filenäme_lo中al rem_veth_se_hehe ____ [let them stay] .this,too elongate "
          "elongate elongate elongate elongate.m4a.txt")
    # selftext written
    with open(os.path.join(tmpdir, "old_user", fn), 'r') as f:
        assert f.read() == ("Title: LEAVE_TITLE_FIELD_UNCHANGED\nPermalink: inserted_rddt3_url\n"
                            "Selftext:\n\nselfff3fffdszlbdftext")

    # reconnect so we make sure it's visible from diff connections
    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()
    assert rows == [tuple(r) for r in expected]


def test_add_to_db(setup_tmpdir):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir

    test_db = os.path.join(tmpdir, "gwarip_db.sqlite")
    test_con, test_c = load_or_create_sql_db(test_db)

    test_c.executescript("""
    BEGIN TRANSACTION;

    INSERT INTO Downloads(
        date, time, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user,
        subreddit_name
        )
    VALUES
        ("2020-01-23", "13:37", "This is a description", "audio_file.m4a",
         "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
         "https://soundgasm.net/sassmastah77/Audio-title-ASMR", NULL,
         NULL, NULL, NULL, NULL, NULL, "sassmastah77", NULL);

    COMMIT;
    """)

    # everything but time col
    query_str = """SELECT
        id, date, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user,
        subreddit_name, rating, favorite FROM Downloads"""

    test_con.close()

    fi = FileInfo(object, True, "m4a", "https://soundgasm.net/testy_user/Best-title-SFW",
                  "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a", None,
                  "Best title [SFW]",
                  "This is another description", "testy_user")
    ri = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                    "26iw32o", "Best title on reddit [SFW]", "testy_ruser",
                    "inserted/subreddit", [fi])
    ri.permalink = "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz"
    ri.selftext = None
    ri.created_utc = 1602557093.0
    ri.subreddit = "pillowtalkaudio"
    ri.r_post_url = "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz"
    fi.parent = ri

    # _add_to_db should NOT commit
    with GWARipper() as gwa:
        gwa._add_to_db(fi, "subpath\\generated [file] [name].mp3")

    expected = [
            [1, "2020-01-23", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", None, None, None],
            ]

    conn = sqlite3.connect(test_db)
    c = conn.execute(query_str)
    rows = c.fetchall()
    conn.close()

    # UNCHANGED!
    assert rows == [tuple(r) for r in expected]

    expected.append(
            [2, time.strftime("%Y-%m-%d"), "This is another description",
             "subpath\\generated [file] [name].mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", "Best title on reddit [SFW]",
             "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz", "testy_ruser",
             "testy_user", "pillowtalkaudio", None, None]
            )

    with GWARipper() as gwa:
        gwa._add_to_db(fi, "subpath\\generated [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    conn = sqlite3.connect(test_db)
    c = conn.execute(query_str)
    rows = c.fetchall()
    conn.close()

    assert rows == [tuple(r) for r in expected]

    expected.append(
            [3, time.strftime("%Y-%m-%d"),
             "Subtitle [SFW]\n\nHello what's up\nSuper duper",
             "filenäme_lo中al rem_veth_se_hehe ____ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate 123.m4a.txt",
             "filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", "https://chirb.it/23sf32", None,
             None, None, None, None, None, "old_user", None, None, None]
            )

    fi = FileInfo(object, True, "mp3", "https://chirb.it/23sf32",
                  "https://no-page-url.com/324q523q.mp3", None,
                  "filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
                  "elongate elongate elongate elongate elongate elongate",
                  "Subtitle [SFW]\n\nHello what's up\nSuper duper", "old_user")

    fn = ("filenäme_lo中al rem_veth_se_hehe ____ [let them stay] .this,too elongate "
          "elongate elongate elongate elongate 123.m4a.txt")

    with GWARipper() as gwa:
        gwa._add_to_db(fi, fn)
        gwa.db_con.commit()  # force commit

    conn = sqlite3.connect(test_db)
    c = conn.execute(query_str)
    rows = c.fetchall()
    conn.close()

    assert rows == [tuple(r) for r in expected]


def test_mark_alrdy_downloaded(setup_tmpdir):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir
    cfg.config["Settings"]["set_missing_reddit"] = "False"

    test_db = os.path.join(tmpdir, "gwarip_db.sqlite")
    test_con, test_c = load_or_create_sql_db(test_db)

    test_c.executescript("""
    BEGIN TRANSACTION;

    INSERT INTO Downloads(
        date, time, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user,
        subreddit_name
        )
    VALUES
        ("2020-01-23", "13:37", "This is a description", "audio_file.m4a",
         "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
         "https://soundgasm.net/sassmastah77/Audio-title-ASMR", NULL,
         NULL, NULL, NULL, NULL, NULL, "sassmastah77", NULL),

        ("2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
         "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
         "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
         "26iw32o", NULL, NULL, NULL, "testy_user", NULL),

        ("2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", NULL,
         "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate elongate elongate elongate elongate elongate elongate",
         "https://no-page-url.com/324q523q.mp3", NULL, 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
         "2klj654", "don_t change this", NULL, NULL, "old_user", NULL);

    COMMIT;
    """)

    test_con.close()

    fi1 = FileInfo(object, True, "m4a", "https://soundgasm.net/sassmastah77/Audio-title-ASMR",
                   "https://soundgasm.net/284291412sa324.m4a", None,
                   "AudiLEAVE_PRESENT_FIELDS_UNCHANGED [ASMR]",
                   "ThisLEAVE_PRESENT_FIELDS_UNCHANGEDion", "LEAVE_PRESENT_FIELDS_UNCHANGED77")
    ri1 = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                     "inserted_reddit_id", "isnerted_reddit_title", "inserted-reddit-user",
                     "inserted/subreddit", [fi1])
    ri1.permalink = "inserted_rddt_url"
    ri1.selftext = None
    ri1.created_utc = 1254323.0
    ri1.subreddit = "ssssubreddit"
    ri1.r_post_url = "url-to-self-or-outgoing"
    fi1.parent = ri1

    # garbage fields for already present col so we can check that they don't get changed
    fi2 = FileInfo(object, True, "m4a", "https://soundgasm.net/testy_user/Best-title-SFW",
                   "https://soundgasm.net/24634adra354.m4a", None,
                   "BeLEAVE_PRESENT_FIELDS_UNCHANGEDe [SFW]",
                   "This iLEAVE_PRESENT_FIELDS_UNCHANGEDscription",
                   "LEAVE_PRESENT_FIELDS_UNCHANGED_user")
    ri2 = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                     "LEAVE_PRESENT_FIELDS_UNCHANGED", "isnerte222d_reddit_title",
                     "inserted-reddit-user", "inserted/subreddit", [fi2])
    ri2.permalink = "inserted_rddt2_url"
    ri2.selftext = "selfff2fffftext"
    ri2.created_utc = 11111111.0
    ri2.r_post_url = "LEAVE_PRESENT_FIELDS_UNCHANGED"
    fi2.parent = ri2

    fi3 = FileInfo(object, True, "m4a", "insertedPAGEURL",
                   "https://no-page-url.com/324q523q.mp3", None,
                   "Use title from DB!",  # needed for selftext fn
                   "This iLEAgsgVE_PRESENT_FIELDS_UNCHANGEDscription",
                   "LEAVE_PRESENT_sgsFIELDS_UNCHANGED_user")
    ri3 = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                     "LEAVE_PRESENT_FIELDS_UNCHANGED", "LEAVE_TITLE_FIELD_UNCHANGED",
                     "inserted-reddit3-user", "inserted3/subreddit", [fi3])
    ri3.permalink = "inserted_rddt3_url"
    ri3.selftext = "selfff3fffdszlbdftext"
    ri3.created_utc = 111111.0
    ri3.r_post_url = "LEAVE_PRESENT_FIELDS_UNCHANGED"
    fi3.parent = ri3

    fi4 = FileInfo(object, True, "mp3", "https://chirb.it/23sf32",
                   "https://no-page-url.com/agfads8392423.mp3", None,
                   "filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
                   "elongate elongate elongate elongate elongate elongate",
                   "Subtitle [SFW]\n\nHello what's up\nSuper duper", "old_user")
    fc4 = FileCollection(object, "skgafd;gaag", None, "akfjglag asdfjlas", "old_user")
    fc4.parent = ri2
    fi4.parent = fc4

    fi5 = FileInfo(object, True, "mp3", "https://chirb.it/asfd25sak27k",
                   "https://chirb.it/agfafsl32923.mp3", None,
                   "20uw0 fowfsdoif20 wdkfj23jr3245",
                   "Kkgads sapofp23 [SFW]\n\nHello what's up\nSuper duper", "super-user")
    ri3.children.append(fi5)
    fi5.parent = ri3

    fi6 = FileInfo(object, True, "mp3", "https://soundcloud.com/2lj4326up034",
                   "https://soundcloud.com/2045tjsaolkfjopi423.mp3", None,
                   "wifjopi345324joi5j34o j34k5jt34kj3o",
                   "LKlk34lk34l0 alfjla0320 [SFW]\n\nHello what's up\nSuper duper",
                   "other.user")

    # nothing should happen
    with GWARipper() as gwa:
        gwa.downloads = [ri1, ri2, fi6, ri3]
        gwa.mark_alrdy_downloaded()

    expected = [
            [1, "2020-01-23", "13:37", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", None, None, None],
            [2, "2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", None, None, None],
            [3, "2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", None, None, None],
            ]

    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()

    assert fi1.already_downloaded
    assert fi2.already_downloaded
    assert fi3.already_downloaded
    assert not fi4.already_downloaded
    assert not fi5.already_downloaded
    assert not fi6.already_downloaded

    # db shouldn't change since set_missing_reddit is False
    assert rows == [tuple(r) for r in expected]

    # reset them
    fi1.already_downloaded = False
    fi2.already_downloaded = False
    fi3.already_downloaded = False
    fi4.already_downloaded = False
    fi5.already_downloaded = False
    fi6.already_downloaded = False

    expected[0][8:16] = [1254323.0, ri1.r_post_url, ri1.id, ri1.title, ri1.permalink,
                         ri1.author, "sassmastah77", ri1.subreddit]

    expected[1][8:16] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                         "26iw32o", ri2.title, ri2.permalink, ri2.author,
                         "testy_user", ri2.subreddit]

    # page url inserted
    expected[2][7] = "insertedPAGEURL"
    expected[2][8:16] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
                         "2klj654", "don_t change this", ri3.permalink, ri3.author,
                         "old_user", ri3.subreddit]

    cfg.config["Settings"]["set_missing_reddit"] = "True"

    with GWARipper() as gwa:
        gwa.downloads = [ri1, ri2, fi6, ri3]
        gwa.mark_alrdy_downloaded()

    conn = sqlite3.connect(test_db)
    c = conn.execute("SELECT * FROM Downloads")
    rows = c.fetchall()
    conn.close()

    assert fi1.already_downloaded
    assert fi2.already_downloaded
    assert fi3.already_downloaded
    assert not fi4.already_downloaded
    assert not fi5.already_downloaded
    assert not fi6.already_downloaded

    # set_missing_reddit called
    assert rows == [tuple(r) for r in expected]
