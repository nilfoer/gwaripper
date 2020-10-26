import pytest
import os
import time
import sqlite3
import logging

import urllib.error

import gwaripper.config as cfg

from gwaripper.gwaripper import GWARipper
from gwaripper.db import load_or_create_sql_db
from gwaripper.info import FileInfo, RedditInfo, FileCollection
from gwaripper.extractors.soundgasm import SoundgasmExtractor
from gwaripper.extractors.reddit import RedditExtractor
from gwaripper.extractors.imgur import ImgurImageExtractor, ImgurAlbumExtractor
from utils import build_file_url, TESTS_DIR, setup_tmpdir, RandomHelper, get_all_rowtuples_db

# TODO?
# test advanced db.py procedures (search_sytnax_parser, etc.)? they're taken from my other project

TESTS_FILES_DIR = os.path.join(TESTS_DIR, "test_dl")


def test_set_missing_reddit(setup_tmpdir):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir

    test_db = os.path.join(tmpdir, "gwarip_db.sqlite")
    test_con, test_c = load_or_create_sql_db(test_db)

    # NOTE: IMPORTANT not inserting value for favorite and later have 0 as expected value
    # so we test that's set as default
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
             None, None, None, None, None, "sassmastah77", None, None, 0],
            [2, "2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", None, None, 0],
            [3, "2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", None, None, 0],
            ]

    query_str = "SELECT * FROM Downloads"

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    fi.parent = ri
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    expected[0][8:16] = [1254323.0, ri.r_post_url, ri.id, ri.title, ri.permalink,
                         ri.author, "sassmastah77", ri.subreddit]
    # selftext not written
    assert os.listdir(tmpdir) == ['gwarip_db.sqlite', 'gwarip_db_exp.csv', '_db-autobu']

    # reconnect so we make sure it's visible from diff connections
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    ri.selftext = "selffffffftext"
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    # selftext written
    with open(os.path.join(tmpdir, "sassmastah77", "audio_file.m4a.txt"), 'r') as f:
        assert f.read() == ("Title: isnerted_reddit_title\nPermalink: inserted_rddt_url\n"
                            "Selftext:\n\nselffffffftext")

    # unchanged rows
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

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
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

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
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


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
             None, None, None, None, None, "sassmastah77", None, None, 0],
            ]

    # UNCHANGED!
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    expected.append(
            [2, time.strftime("%Y-%m-%d"), "This is another description",
             "subpath\\generated [file] [name].mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", "Best title on reddit [SFW]",
             "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz", "testy_ruser",
             "testy_user", "pillowtalkaudio", None, 0]
            )

    with GWARipper() as gwa:
        gwa._add_to_db(fi, "subpath\\generated [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    expected.append(
            [3, time.strftime("%Y-%m-%d"),
             "Subtitle [SFW]\n\nHello what's up\nSuper duper",
             "filenäme_lo中al rem_veth_se_hehe ____ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate 123.m4a.txt",
             "filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", "https://chirb.it/23sf32", None,
             None, None, None, None, None, "old_user", None, None, 0]
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

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


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

    #
    #
    #

    expected = [
            [1, "2020-01-23", "13:37", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", None, None, 0],
            [2, "2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", None, None, 0],
            [3, "2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", None, None, 0],
            ]

    query_str = "SELECT * FROM Downloads"

    # db shouldn't change since set_missing_reddit is False
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    assert fi1.already_downloaded
    assert fi2.already_downloaded
    assert fi3.already_downloaded
    assert not fi4.already_downloaded
    assert not fi5.already_downloaded
    assert not fi6.already_downloaded

    # reset them
    fi1.already_downloaded = False
    fi2.already_downloaded = False
    fi3.already_downloaded = False
    fi4.already_downloaded = False
    fi5.already_downloaded = False
    fi6.already_downloaded = False

    #
    #
    #

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

    # set_missing_reddit called
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    assert fi1.already_downloaded
    assert fi2.already_downloaded
    assert fi3.already_downloaded
    assert not fi4.already_downloaded
    assert not fi5.already_downloaded
    assert not fi6.already_downloaded


def test_download(setup_tmpdir, monkeypatch, caplog):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir

    rnd = RandomHelper()

    test_db = os.path.join(tmpdir, "gwarip_db.sqlite")
    test_con, test_c = load_or_create_sql_db(test_db)

    testdl_files = os.path.join(tmpdir, "_testdls")
    os.makedirs(testdl_files)

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

    expected = [
            [1, "2020-01-23", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", None, None, 0],
            [2, "2020-12-13", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", None, None, 0],
            [3, "2020-12-15", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", None, None, 0],
            ]

    # everything but time col
    query_str = """SELECT
        id, date, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user,
        subreddit_name, rating, favorite FROM Downloads"""

    test_con.close()

    fi_file_contents = []
    for i in range(5):
        fi_file_contents.append(rnd.random_string(100))
        with open(os.path.join(testdl_files,  f"fi{i}"), "w") as f:
            f.write(fi_file_contents[i])

    # so first file name gets incremented
    os.makedirs(os.path.join(tmpdir, "page_user"))
    dont_overwrite_file = os.path.join(tmpdir, "page_user",  "dont_overwrite.jpg")
    with open(dont_overwrite_file, "w") as f:
        f.write("not overwritten")

    fi0 = FileInfo(object, False, "jpg", "https://page.url/al3234653",
                   build_file_url(os.path.join(testdl_files, "fi0")), None,  # id
                   "dont_overwrite",  # title
                   "This is the description fi0", "page_user")

    # non audio file should not be added to db - only downloaded
    with GWARipper() as gwa:
        gwa.nr_downloads = 3
        gwa.download(fi0)
        assert gwa.download_index == 2  # _NEXT_ download idx
        assert fi0.downloaded is True

    with open(dont_overwrite_file, "r") as f:
        assert f.read() == "not overwritten"

    # padded with number
    with open(os.path.join(tmpdir, fi0.author, "dont_overwrite_02.jpg"), "r") as f:
        assert f.read() == fi_file_contents[0]

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]
    
    #
    #
    #

    fi1 = FileInfo(object, True, "m4a", "https://page.url/al323asf4653",
                   build_file_url(os.path.join(testdl_files, "fi1")), None,  # id
                   rnd.random_string(20),  # title
                   rnd.random_string(50), "dummy_usr")

    # testing file has already_downloaded set
    fi1.already_downloaded = True
    with GWARipper() as gwa:
        gwa.nr_downloads = 3
        gwa.download(fi1)
        assert gwa.nr_downloads == 2
        assert fi1.downloaded is False

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    fi1.already_downloaded = False
    fi1_fn = f"{fi1.title}.{fi1.ext}"
    expected.append(
            [4, time.strftime("%Y-%m-%d"), fi1.descr, fi1_fn,
             fi1.title, fi1.direct_url, fi1.page_url, None, None, None, None,
             None, None, fi1.author, None, None, 0]
            )

    with GWARipper() as gwa:
        gwa.nr_downloads = 3
        gwa.download(fi1)
        assert gwa.download_index == 2  # _NEXT_ download idx
        assert fi1.downloaded is True

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    with open(os.path.join(tmpdir, fi1.author, fi1_fn), "r") as f:
        assert f.read() == fi_file_contents[1]

    #
    #
    #

    # fi1 = FileInfo(object, True, "ext", "https://page.url/al3234653",
    #                "https://direct.url/24sff3j3l434520.ext", None,  # id
    #                "Onpage title",
    #                "This is the description", "page_user")
    # ri2 = RedditInfo(object, "url-not-used-when-adding-to-db",
    #                  "r3dd1tid", "Best title on reddit [SFW]", "reddit_user",
    #                  "subreddit", [fi1])
    fi2 = FileInfo(object, True, "m4a", "https://page.url/2l345jsaofjso932",
                   build_file_url(os.path.join(testdl_files, "fi2")), None,  # id
                   rnd.random_string(20),  # title
                   rnd.random_string(50), "other-than_rddt-usr")
    fi2_fn = f"Reddit_title _ as sub_path_01_{fi2.title}.{fi2.ext}"
    fi3 = FileInfo(object, True, "mp3", "https://page.url/242lk2598242jrtn3l4",
                   build_file_url(os.path.join(testdl_files, "fi3")), None,  # id
                   "[Foo] Bar qux ❤",  # title
                   rnd.random_string(50), "other-than_rddt-usr")
    fi3_fn = f"Prepended title_01_[Foo] Bar qux _.{fi3.ext}"
    # extr, url, id
    fc1 = FileCollection(object, rnd.random_string(30), rnd.random_string(7),
                         "Prepended title", "other-than_rddt-usr2",
                         [fi3])
    fi4 = FileInfo(object, False, "gif", "https://page.url/245j2l56t2098432",
                   build_file_url(os.path.join(testdl_files, "fi4")), rnd.random_string(5),  # id
                   "non-audio_file",  # title
                   None, "other-than_rddt-usr3")
    fi4_fn = f"Reddit_title _ as sub_path_02_{fi4.title}.{fi4.ext}"
    ri1 = RedditInfo(object, "https://dont-use-this-url/in-db",
                     rnd.random_string(6), "Reddit:title / as sub\\path", "reddit_user",
                     rnd.random_string(15), [fi2, fc1, fi4])
    ri1.permalink = "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz"
    ri1.selftext = "selftext_should not have been written"
    ri1.created_utc = 1602557093.0
    ri1.r_post_url = "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz"
    # set parent
    fi2.parent = ri1
    fi3.parent = fc1
    fc1.parent = ri1
    fi4.parent = ri1
    # set already downloaded so collection gets skipped
    fi2.already_downloaded = True
    fi3.already_downloaded = True
    fi4.already_downloaded = True

    with GWARipper() as gwa:
        gwa.nr_downloads = 3
        gwa.download(ri1)
        assert gwa.nr_downloads == 0

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    # assure that no seltext was written when collections was skipped
    for dirpath, dirs, files in os.walk(tmpdir):
        for fn in (f for f in files if f.endswith(".txt")):
            with open(os.path.join(dirpath, fn), "r") as f:
                assert ri1.selftext not in f.read()

    #
    #
    #

    ri1.selftext = "this selftext should be written !!!!"
    # reset already downloaded
    fi2.already_downloaded = False
    fi3.already_downloaded = False
    fi4.already_downloaded = False

    expected.extend([
            [5, time.strftime("%Y-%m-%d"), fi2.descr, fi2_fn,
             fi2.title, fi2.direct_url, fi2.page_url, ri1.created_utc, ri1.r_post_url,
             ri1.id, ri1.title, ri1.permalink,  ri1.author, fi2.author, ri1.subreddit,
             None, 0],
            [6, time.strftime("%Y-%m-%d"), fi3.descr, fi3_fn,
             fi3.title, fi3.direct_url, fi3.page_url, ri1.created_utc, ri1.r_post_url,
             ri1.id, ri1.title, ri1.permalink,  ri1.author, fi3.author, ri1.subreddit,
             None, 0],
            ])

    with GWARipper() as gwa:
        gwa.nr_downloads = 3
        gwa.download(ri1)
        assert gwa.download_index == 4  # _NEXT_ download idx

    assert fi2.downloaded
    assert fi3.downloaded
    assert fi4.downloaded

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    ri1_dir = os.path.join(tmpdir, ri1.author, "Reddit_title _ as sub_path")
    # selftext
    with open(os.path.join(ri1_dir, "Reddit_title _ as sub_path.txt"), "r") as f:
        assert f.read() == (
                f"Title: {ri1.title}\nPermalink: {ri1.permalink}\nSelftext:\n\n{ri1.selftext}")
    fns = [None, fi1_fn, fi2_fn, fi3_fn, fi4_fn]
    for i in range(2, 5):
        with open(os.path.join(ri1_dir, fns[i]), "r") as f:
            assert f.read() == fi_file_contents[i]

    # reuse fi4 since it wasn't added to db but with diff parent
    fi4.downloaded = False
    fi4.is_audio = True
    fi4.ext = "wav"
    fi4_fn = f"FC2 _ Prep_ended ti_tle_{fi4.title}.{fi4.ext}"
    expected.append(
            [7, time.strftime("%Y-%m-%d"), fi4.descr, fi4_fn,
             fi4.title, fi4.direct_url, fi4.page_url, None, None,
             None, None, None,  None, fi4.author, None, None, 0]
            )

    # extr, url, id
    fc2 = FileCollection(object, rnd.random_string(30), rnd.random_string(7),
                         "FC2 ? Prep/ended ti:tle", "fcol_author",
                         [fi4])
    fi4.parent = fc2
    assert fi4.reddit_info is None  # just to be sure

    with GWARipper() as gwa:
        gwa.nr_downloads = 1
        gwa.download(fc2)
        assert gwa.download_index == 2  # _NEXT_ download idx

    assert fi4.downloaded

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    fc2_dir = os.path.join(tmpdir, fc2.author)
    with open(os.path.join(fc2_dir, fi4_fn), "r") as f:
        assert f.read() == fi_file_contents[4]

    fi5 = FileInfo(SoundgasmExtractor, False, "gif", "https://page.url/asjfgl3oi5j23",
                   build_file_url(os.path.join(testdl_files, "fi5")), rnd.random_string(5),  # id
                   "should raise",  # title
                   None, "exceptional")

    caplog.clear()
    caplog.set_level(logging.WARNING)

    with GWARipper() as gwa:
        gwa.nr_downloads = 1
        gwa.download(fi5)
        assert gwa.download_index == 2  # _NEXT_ download idx

    logs = "\n".join(rec.message for rec in caplog.records)
    assert ("Extractor <class 'gwaripper.extractors.soundgasm.SoundgasmExtractor'> "
            "is probably broken") in logs

    assert fi5.downloaded is False

    # should not commit adding fi5 to db!!
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    def always_raise_cts(url, fn, headers=None, prog_bar=None):
        raise urllib.error.ContentTooShortError("Content too short!", None)

    monkeypatch.setattr('gwaripper.download.download_in_chunks', always_raise_cts)

    caplog.clear()

    with GWARipper() as gwa:
        gwa.nr_downloads = 1
        gwa.download(fi5)
        assert gwa.download_index == 2  # _NEXT_ download idx

    logs = "\n".join(rec.message for rec in caplog.records)

    assert fi5.downloaded is False
    assert "not added to DB" in logs
    assert "selftext might not be written" in logs
    assert "manually delete and re-download" in logs

    # should not commit adding fi5 to db!!
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


def test_parse_links(setup_tmpdir, monkeypatch, caplog):
    tmpdir = setup_tmpdir
    cfg.ROOTDIR = tmpdir

    soundgasmfi = FileInfo(SoundgasmExtractor, False, "gif", "https://page.url/asjfgl3oi5j23",
                           'https://page.url/asjfgl3oi5j23/file.mp3', "sfkjl",  # id
                           "Title",  # title
                           None, "author")
    monkeypatch.setattr('gwaripper.extractors.soundgasm.SoundgasmExtractor.extract',
                        lambda x: soundgasmfi)
    imgurmimgfi = FileInfo(ImgurImageExtractor, None, None, "url",
                           "direct url", None, None, None, None)
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurImageExtractor.extract',
                        lambda x: imgurmimgfi)
    imguralbumfc = FileCollection(ImgurAlbumExtractor, "https://imgur.com/a/k23j4", "k23j4",
                                  "Test", "author", [imgurmimgfi, imgurmimgfi])
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurAlbumExtractor.extract',
                        lambda x: imguralbumfc)
    redditinfo = RedditInfo(RedditExtractor, "url", "id", "title",
                            'author', 'subreddit', [soundgasmfi, imguralbumfc])
    monkeypatch.setattr('gwaripper.extractors.reddit.RedditExtractor.extract',
                        lambda x: redditinfo)
    monkeypatch.setattr('gwaripper.extractors.chirbit.ChirbitExtractor.extract',
                        lambda x: None)

    # expected = [
    #         redditinfo,
    #         soundgasmfi
    #         ]

    # include duplictate urls
    urls = [
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://no-supported.found/id/243kwd/',
            'https://chirb.it/hnz5aB',  # returns None
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            ]

    with GWARipper() as gwa:
        gwa.parse_links(urls)

    assert gwa.nr_downloads == 4
    assert f"Skipping URL: {urls[2]}" in caplog.text
    # no comparison operators defined currently can't sort and compare list
    assert len(gwa.downloads) == 2
    assert redditinfo in gwa.downloads
    assert soundgasmfi in gwa.downloads
