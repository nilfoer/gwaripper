import pytest
import os
import time
import sqlite3
import logging

import urllib.error

import gwaripper.config as cfg

from gwaripper.gwaripper import GWARipper, report_preamble
from gwaripper.db import load_or_create_sql_db
from gwaripper.info import FileInfo, RedditInfo, FileCollection
from gwaripper.extractors.base import ExtractorReport, ExtractorErrorCode
from gwaripper.extractors.soundgasm import SoundgasmExtractor
from gwaripper.extractors.reddit import RedditExtractor
from gwaripper.extractors.imgur import ImgurImageExtractor, ImgurAlbumExtractor
from gwaripper.exceptions import InfoExtractingError
from utils import build_file_url, TESTS_DIR, setup_tmpdir, RandomHelper, get_all_rowtuples_db

# TODO?
# test advanced db.py procedures (search_sytnax_parser, etc.)? they're taken from my other project

TESTS_FILES_DIR = os.path.join(TESTS_DIR, "test_dl")


def test_set_missing_reddit(setup_tmpdir):
    tmpdir = setup_tmpdir

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
                    "inserted/subreddit", 'inserted_rddt_url', 1254323.0, children=[fi])
    ri.selftext = None
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
                    "inserted-reddit-user", "inserted/subreddit", "inserted_rddt2_url",
                    11111111.0, [fi])
    ri.selftext = "selfff2fffftext"
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
                    "inserted-reddit3-user", "inserted3/subreddit", "inserted_rddt3_url",
                    111111.0, [fi])
    ri.selftext = "selfff3fffdszlbdftext"
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
                    "pillowtalkaudio", "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                    1602557093.0, [fi])
    ri.selftext = None
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


def test_already_downloaded(setup_tmpdir):
    tmpdir = setup_tmpdir
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
                     "ssssubreddit", "inserted_rddt_url", 1254323.0, [fi1])
    ri1.selftext = None
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
                     "inserted-reddit-user", "inserted/subreddit", "inserted_rddt2_url",
                     11111111.0, [fi2])
    ri2.selftext = "selfff2fffftext"
    ri2.r_post_url = "LEAVE_PRESENT_FIELDS_UNCHANGED"
    fi2.parent = ri2

    fi3 = FileInfo(object, True, "m4a", "insertedPAGEURL",
                   "https://no-page-url.com/324q523q.mp3", None,
                   "Use title from DB!",  # needed for selftext fn
                   "This iLEAgsgVE_PRESENT_FIELDS_UNCHANGEDscription",
                   "LEAVE_PRESENT_sgsFIELDS_UNCHANGED_user")
    ri3 = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                     "LEAVE_PRESENT_FIELDS_UNCHANGED", "LEAVE_TITLE_FIELD_UNCHANGED",
                     "inserted-reddit3-user", "inserted3/subreddit", "inserted_rddt3_url",
                     111111.0, [fi3])
    ri3.selftext = "selfff3fffdszlbdftext"
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
        assert gwa.already_downloaded(fi1)
        assert fi1.already_downloaded

        assert gwa.already_downloaded(fi2)
        assert fi2.already_downloaded

        assert gwa.already_downloaded(fi3)
        assert fi3.already_downloaded

        assert not gwa.already_downloaded(fi4)
        assert not fi4.already_downloaded

        assert not gwa.already_downloaded(fi5)
        assert not fi5.already_downloaded

        assert not gwa.already_downloaded(fi6)
        assert not fi6.already_downloaded

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
        assert gwa.already_downloaded(fi1)
        assert fi1.already_downloaded

        assert gwa.already_downloaded(fi2)
        assert fi2.already_downloaded

        assert gwa.already_downloaded(fi3)
        assert fi3.already_downloaded

        assert not gwa.already_downloaded(fi4)
        assert not fi4.already_downloaded

        assert not gwa.already_downloaded(fi5)
        assert not fi5.already_downloaded

        assert not gwa.already_downloaded(fi6)
        assert not fi6.already_downloaded

    # set_missing_reddit called
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


def test_download(setup_tmpdir, monkeypatch, caplog):
    tmpdir = setup_tmpdir

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
        gwa.download(fi0)
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

    bu_already_dled = GWARipper.already_downloaded
    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.already_downloaded',
                        lambda x, fi: True)
    fi1 = FileInfo(object, True, "m4a", "https://page.url/al323asf4653",
                   build_file_url(os.path.join(testdl_files, "fi1")), None,  # id
                   rnd.random_string(20),  # title
                   rnd.random_string(50), "dummy_usr")

    # testing file has already_downloaded set
    assert fi1.downloaded is False
    with GWARipper() as gwa:
        gwa.download(fi1)
        assert fi1.downloaded is False

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.already_downloaded',
                        bu_already_dled)
    fi1_fn = f"{fi1.title}.{fi1.ext}"
    expected.append(
            [4, time.strftime("%Y-%m-%d"), fi1.descr, fi1_fn,
             fi1.title, fi1.direct_url, fi1.page_url, None, None, None, None,
             None, None, fi1.author, None, None, 0]
            )

    with GWARipper() as gwa:
        gwa.download(fi1)
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
    #                  "subreddit", [fi1])  MISSING permalink+created_utc
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
                     rnd.random_string(15), "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                     1602557093.0, [fi2, fc1, fi4])
    ri1.selftext = "selftext_should not have been written"
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

    def patched_alrdy_dled(self, fi):
        if fi is fi2 or fi is fi3 or fi is fi4:
            return True
        else:
            return False

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.already_downloaded',
                        patched_alrdy_dled)

    with GWARipper() as gwa:
        gwa.download(ri1)

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    # assure that no seltext was written when collections was skipped
    for dirpath, dirs, files in os.walk(tmpdir):
        for fn in (f for f in files if f.endswith(".txt")):
            with open(os.path.join(dirpath, fn), "r") as f:
                assert ri1.selftext not in f.read()

    #
    #
    #

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.already_downloaded',
                        bu_already_dled)

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
        gwa.download(ri1)

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
        gwa.download(fc2)

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
        gwa.download(fi5)

    assert ("Extractor gwaripper.extractors.soundgasm.SoundgasmExtractor is probably "
            "broken! Please report this error on github!") in caplog.text

    assert fi5.downloaded is False

    # should not commit adding fi5 to db!!
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    def always_raise_cts(url, fn, headers=None, prog_bar=None):
        raise urllib.error.ContentTooShortError("Content too short!", None)

    monkeypatch.setattr('gwaripper.download.download_in_chunks', always_raise_cts)

    caplog.clear()

    with GWARipper() as gwa:
        gwa.download(fi5)

    logs = "\n".join(rec.message for rec in caplog.records)

    assert fi5.downloaded is False
    assert "not added to DB" in logs
    assert "selftext might not be written" in logs
    assert "manually delete and re-download" in logs

    # should not commit adding fi5 to db!!
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


def test_set_urls(setup_tmpdir):
    tmpdir = setup_tmpdir

    urls = [
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://no-supported.found/id/243kwd/',
            'https://chirb.it/hnz5aB',  # returns None
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            'https://www.eraudica.com/e/eve/2015/Escaped-Audio-Title-Eraudica/gwa',
            ]

    expected = [
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://no-supported.found/id/243kwd/',
            'https://chirb.it/hnz5aB',  # returns None
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            'https://www.eraudica.com/e/eve/2015/Escaped-Audio-Title-Eraudica/gwa',
            ]

    with GWARipper() as gwa:
        gwa.set_urls(urls)
        assert sorted(gwa.urls) == sorted(expected)
        assert gwa.nr_urls == 5


def test_extract_and_download(setup_tmpdir, monkeypatch, caplog):
    # setup_tmpdir sets root_path in config
    tmpdir = setup_tmpdir

    soundgasmfi = FileInfo(SoundgasmExtractor, False, "gif", "https://page.url/asjfgl3oi5j23",
                           'https://page.url/asjfgl3oi5j23/file.mp3', "sfkjl",  # id
                           "Title",  # title
                           None, "author")
    soundgasmrep = ExtractorReport(soundgasmfi.page_url, ExtractorErrorCode.NO_ERRORS)
    monkeypatch.setattr('gwaripper.extractors.soundgasm.SoundgasmExtractor._extract',
                        lambda x: (soundgasmfi, soundgasmrep))

    imgurmimgfi = FileInfo(ImgurImageExtractor, None, None, "url",
                           "direct url", None, None, None, None)
    imgurimgrep = ExtractorReport(imgurmimgfi.page_url, ExtractorErrorCode.NO_ERRORS)
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurImageExtractor._extract',
                        lambda x: (imgurmimgfi, imgurimgrep))

    imguralbumfc = FileCollection(ImgurAlbumExtractor, "https://imgur.com/a/k23j4", "k23j4",
                                  "Test", "author", [imgurmimgfi, imgurmimgfi])
    imguralbumrep = ExtractorReport(imguralbumfc.url, ExtractorErrorCode.NO_ERRORS)
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurAlbumExtractor._extract',
                        lambda x: (imguralbumfc, imguralbumrep))

    redditinfo = RedditInfo(RedditExtractor, "url", "id", "title",
                            'author', 'subreddit', 'permalink', 12345.0,
                            [soundgasmfi, imguralbumfc])
    redditinforep = ExtractorReport(redditinfo.url, ExtractorErrorCode.NO_ERRORS)
    monkeypatch.setattr('gwaripper.extractors.reddit.RedditExtractor._extract',
                        lambda x: (redditinfo, redditinforep))

    # monkeypatch.setattr('gwaripper.extractors.chirbit.ChirbitExtractor._extract',
    #                     lambda x: (None,
    #                                ExtractorReport('https://chirb.it/hnz5aB',
    #                                                ExtractorErrorCode.NO_RESPONSE)))
    monkeypatch.setattr('gwaripper.extractors.chirbit.ChirbitExtractor.get_html',
                        # return no html with 408 http code for timeout
                        lambda url: (None, 408))

    # extract_and_download should not crash on any exception since it uses BaseExtractor.extract
    def raises(self):
        raise FileNotFoundError()

    monkeypatch.setattr('gwaripper.extractors.eraudica.EraudicaExtractor._extract',
                        raises)

    # include duplictate urls
    urls = [
            'https://old.reddit.com/r/gonewildaudio/comments/jia91q/escaped_title_string/',
            'https://soundgasm.net/user/UserName/Escaped-Audio-Title',
            'https://no-supported.found/id/243kwd/',
            'https://chirb.it/hnz5aB',  # returns None
            'https://www.eraudica.com/e/eve/2015/Escaped-Audio-Title-Eraudica/gwa',
            ]

    download_called_with = None

    def patched_dl(self, fi):
        assert fi is not None
        nonlocal download_called_with
        download_called_with = fi
        fi.downloaded = True

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    with GWARipper() as gwa:
        gwa.extract_and_download(urls[0])
        # extr report appended and downloaded set
        assert gwa.extractor_reports[0] is redditinforep
        assert gwa.extractor_reports[0].downloaded is True
        assert len(gwa.extractor_reports) == 1
    # download called
    assert download_called_with is redditinfo
    assert download_called_with.downloaded is True

    def patched_dl(self, fi):
        assert fi is not None
        nonlocal download_called_with
        download_called_with = fi

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    with GWARipper() as gwa:
        gwa.extract_and_download(urls[1])
        # extr report appended and downloaded set
        assert gwa.extractor_reports[0] is soundgasmrep
        assert gwa.extractor_reports[0].downloaded is False
        assert len(gwa.extractor_reports) == 1
    # download called
    assert download_called_with is soundgasmfi
    assert download_called_with.downloaded is False

    #
    # no supported extr found
    #
    caplog.clear()
    caplog.set_level(logging.WARNING)
    download_called_with = None
    with GWARipper() as gwa:
        gwa.extract_and_download(urls[2])
        # extr report appended and downloaded set
        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0].err_code == ExtractorErrorCode.NO_EXTRACTOR
        assert gwa.extractor_reports[0].url == urls[2]
        assert gwa.extractor_reports[0].downloaded is False

        # needs to be inside context otherwise db auto bu is run and logs msg
        assert len(caplog.records) == 1
        assert caplog.records[0].message == f'Found no extractor for URL: {urls[2]}'
    # download not called
    assert download_called_with is None

    #
    # extractor returns None due to timeout
    #
    caplog.clear()
    caplog.set_level(logging.WARNING)
    download_called_with = None
    with GWARipper() as gwa:
        gwa.extract_and_download(urls[3])
        # extr report appended and downloaded set
        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0].err_code == ExtractorErrorCode.NO_RESPONSE
        assert gwa.extractor_reports[0].url == urls[3]
        assert gwa.extractor_reports[0].downloaded is False

        # needs to be inside context otherwise db auto bu is run and logs msg
        assert len(caplog.records) == 1
        assert (f"ERROR - NO_RESPONSE - Request timed out or no response received! "
                f"(URL was {urls[3]})") == caplog.records[0].message
    # download not called
    assert download_called_with is None

    #
    # broken extractor first and second run
    #

    caplog.clear()
    caplog.set_level(logging.WARNING)
    download_called_with = None
    with GWARipper() as gwa:
        # 1st time exc in eraudica extr
        gwa.extract_and_download(urls[4])
        # extr report appended and downloaded set
        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0].err_code == ExtractorErrorCode.BROKEN_EXTRACTOR
        assert gwa.extractor_reports[0].url == urls[4]
        assert gwa.extractor_reports[0].downloaded is False
        # download not called
        assert download_called_with is None

        # needs to be inside context otherwise db auto bu is run and logs msg
        assert len(caplog.records) == 2
        assert (f"Error occured while extracting information from '{urls[4]}' "
                "- site structure or API probably changed! See if there are "
                "updates available!") == caplog.records[0].message
        # pytest fails to capture logging exception information the pytest logging hook
        # crashed/raised instead
        # assert ("Full exception info for unexpected extraction failure:") in caplog.text
        # assert "in raises" in caplog.text
        # assert "raise FileNotFoundError()" in caplog.text

        # 2nd time eraudica extr already marked as broken
        caplog.clear()
        gwa.extract_and_download(urls[4])
        # extr report appended and downloaded set
        assert len(gwa.extractor_reports) == 2
        assert gwa.extractor_reports[1].err_code == ExtractorErrorCode.BROKEN_EXTRACTOR
        assert gwa.extractor_reports[1].url == urls[4]
        assert gwa.extractor_reports[1].downloaded is False
        # download not called
        assert download_called_with is None

        assert len(caplog.records) == 1
        assert caplog.records[0].message == (
                f"Skipping URL '{urls[4]}' due to broken extractor: Eraudica")


class DummySub:
    permalink = 'permalink'


def test_parse_and_download_submission(setup_tmpdir, monkeypatch):

    download_called_with = None

    def patched_dl(self, fi):
        assert fi is not None
        nonlocal download_called_with
        download_called_with = fi
        fi.downloaded = True

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    redditinfo = RedditInfo(RedditExtractor, "url", "id", "title",
                            'author', 'subreddit', 'permalink', 12345.0)
    redditinfo_permalink = redditinfo.permalink
    redditinforep = ExtractorReport(redditinfo.url, ExtractorErrorCode.NO_ERRORS)
    sub = DummySub()

    def patched_extr(url, init_from=None):
        assert init_from is sub
        assert url == f"https://www.reddit.com{redditinfo_permalink}"
        return redditinfo, redditinforep

    monkeypatch.setattr('gwaripper.extractors.reddit.RedditExtractor.extract',
                        patched_extr)

    with GWARipper() as gwa:
        gwa.parse_and_download_submission(sub)
        assert download_called_with is redditinfo
        assert redditinfo.downloaded is True

        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0] is redditinforep
        assert gwa.extractor_reports[0].downloaded is redditinfo.downloaded

    # TODO extr ret none
    download_called_with = None

    def patched_dl(self, fi):
        assert fi is not None
        nonlocal download_called_with
        download_called_with = fi

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    redditinfo = None
    redditinforep = ExtractorReport('banned_tag', ExtractorErrorCode.BANNED_TAG)

    with GWARipper() as gwa:
        gwa.parse_and_download_submission(sub)
        # dl not called
        assert download_called_with is None

        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0] is redditinforep
        assert gwa.extractor_reports[0].downloaded is False


def test_pad_filename(setup_tmpdir, caplog):
    tmpdir = setup_tmpdir

    # create some files
    open(os.path.join(tmpdir, 'test.txt'), 'w').close()
    open(os.path.join(tmpdir, 'test_01.txt'), 'w').close()
    open(os.path.join(tmpdir, 'test_02.txt'), 'w').close()
    open(os.path.join(tmpdir, 'test_04.txt'), 'w').close()

    open(os.path.join(tmpdir, 'foo.bar.txt'), 'w').close()
    open(os.path.join(tmpdir, 'foo.bar_02.txt'), 'w').close()

    caplog.set_level(logging.INFO)
    caplog.clear()
    with GWARipper() as gwa:
        assert gwa._pad_filename_if_exits(tmpdir, 'test', 'txt') == 'test_03'
        assert caplog.records[0].message == 'FILE ALREADY EXISTS - ADDED: _03'

        caplog.clear()
        assert gwa._pad_filename_if_exits(tmpdir, 'foo', 'bar.txt') == 'foo_02'
        assert caplog.records[0].message == 'FILE ALREADY EXISTS - ADDED: _02'

        assert gwa._pad_filename_if_exits(tmpdir, 'baz', '.m4a') == 'baz'


def test_write_report(setup_tmpdir):
    tmpdir = setup_tmpdir

    ecode = ExtractorErrorCode
    reports = [
            ExtractorReport('url1', ecode.NO_ERRORS),
            ExtractorReport('url2col', ecode.ERROR_IN_CHILDREN),
            ExtractorReport('url3', ecode.BANNED_TAG),
            ExtractorReport('url4col', ecode.NO_SUPPORTED_AUDIO_LINK)
            ]

    reports[0].downloaded = True
    reports[1].downloaded = False
    reports[2].downloaded = False
    reports[3].downloaded = False

    reports[1].children = [
            ExtractorReport('url2colurl1', ecode.NO_RESPONSE),
            ExtractorReport('url2colurl2', ecode.NO_EXTRACTOR),
            ExtractorReport('url2colurl3col', ecode.ERROR_IN_CHILDREN),
            ]

    reports[1].children[0].downloaded = False
    reports[1].children[1].downloaded = False
    reports[1].children[2].downloaded = False

    reports[1].children[2].children = [
            ExtractorReport('url2colurl3colurl1', ecode.NO_AUTHENTICATION),
            ExtractorReport('url2colurl3colurl2', ecode.NO_ERRORS),
            ]

    reports[1].children[2].children[0].downloaded = False
    reports[1].children[2].children[1].downloaded = True

    reports[3].children = [
            ExtractorReport('url4colurl1', ecode.NO_ERRORS),
            ExtractorReport('url4colurl2', ecode.BANNED_TAG),
            ]

    reports[3].children[0].downloaded = True
    reports[3].children[1].downloaded = False

    expected = [
            report_preamble,
            "<div class=\"block \">",
            "<a href=\"url1\">url1</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"collection \">",
            "<span>Collection: </span><a href=\"url2col\">url2col</a>",
            "<div class='info'><span class='error '>ERROR_IN_CHILDREN</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl1\">url2colurl1</a>",
            "<div class='info'><span class='error '>NO_RESPONSE</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl2\">url2colurl2</a>",
            "<div class='info'><span class='error '>NO_EXTRACTOR</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"collection indent \">",
            "<span>Collection: </span><a href=\"url2colurl3col\">url2colurl3col</a>",
            "<div class='info'><span class='error '>ERROR_IN_CHILDREN</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl3colurl1\">url2colurl3colurl1</a>",
            "<div class='info'><span class='error '>NO_AUTHENTICATION</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl3colurl2\">url2colurl3colurl2</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>DOWNLOADED</span></div>",
            "</div>",
            "</div>",  # urlcol2url3col
            "</div>",  # url2col
            "<div class=\"block \">",
            "<a href=\"url3\">url3</a>",
            "<div class='info'><span class='error '>BANNED_TAG</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"collection \">",
            "<span>Collection: </span><a href=\"url4col\">url4col</a>",
            "<div class='info'><span class='error '>NO_SUPPORTED_AUDIO_LINK</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url4colurl1\">url4colurl1</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url4colurl2\">url4colurl2</a>",
            "<div class='info'><span class='error '>BANNED_TAG</span></div>",
            "<div class='info'><span class='error '>NOT DOWNLOADED</span></div>",
            "</div>",
            "</div>",  # url4col
    ]

    with GWARipper() as g:
        g.write_report(reports)

    expected_str = "\n".join(expected)
    with open(
            os.path.join(tmpdir, "_reports",
                         f"report_{time.strftime('%Y-%m-%dT%Hh%Mm')}.html"),
            "r") as f:
        assert expected_str == f.read()
