import pytest
import os
import time
import sqlite3
import logging
import datetime

import urllib.error

import gwaripper.config as cfg

from gwaripper.gwaripper import GWARipper, report_preamble
from gwaripper.db import load_or_create_sql_db
from gwaripper.info import FileInfo, RedditInfo, FileCollection, DELETED_USR_FOLDER
from gwaripper.extractors.base import ExtractorReport, ExtractorErrorCode
from gwaripper.extractors.soundgasm import SoundgasmExtractor
from gwaripper.extractors.reddit import RedditExtractor
from gwaripper.extractors.imgur import ImgurImageExtractor, ImgurAlbumExtractor
from gwaripper.exceptions import InfoExtractingError
from utils import build_file_url, TESTS_DIR, setup_tmpdir, RandomHelper, get_all_rowtuples_db

# TODO?
# test advanced db.py procedures (search_sytnax_parser, etc.)? they're taken from my other project

TESTS_FILES_DIR = os.path.join(TESTS_DIR, "test_dl")


def test_exit_context(setup_tmpdir, monkeypatch):
    tmpdir = setup_tmpdir

    exp_csv_called = False

    def patch_exp_csv(con, fn, table):
        assert fn == os.path.join(tmpdir, 'gwarip_db_exp.csv')
        assert con
        assert table == "v_audio_and_collection_combined"
        nonlocal exp_csv_called
        exp_csv_called = True

    # gwaripper.py used from .. import .. so it's in it's own 'namespace'
    # so we have to patch it there
    monkeypatch.setattr('gwaripper.gwaripper.export_table_to_csv', patch_exp_csv)

    close_called = False

    class DummyCon:
        def close(self):
            nonlocal close_called
            close_called = True

    write_report_called = False

    reports = [ExtractorReport('url', ExtractorErrorCode.NO_EXTRACTOR)]

    def patch_write_rep(self, reps):
        assert reps is reports
        nonlocal write_report_called
        write_report_called = True

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.write_report', patch_write_rep)

    backup_db_called = False

    def patched_backup_db(fn_in, dir_out):
        assert fn_in == os.path.join(tmpdir, 'gwarip_db.sqlite')
        assert dir_out == os.path.join(tmpdir, '_db-autobu')
        nonlocal backup_db_called
        backup_db_called = True

    monkeypatch.setattr('gwaripper.gwaripper.backup_db', patched_backup_db)

    # exit should: call export to csv, write reports, auto bu db, close db con
    with GWARipper() as gwa:
        gwa.db_con = DummyCon()
        gwa.extractor_reports = reports
    assert exp_csv_called is True
    assert close_called is True
    assert write_report_called is True
    assert backup_db_called is True

    # dont call write reports if no reports
    write_report_called = False
    with GWARipper() as gwa:
        gwa.db_con = DummyCon()
    assert write_report_called is False


@pytest.fixture
def setup_db_2col_5audio(setup_tmpdir):
    return _setup_db_2col_5audio(setup_tmpdir)


@pytest.fixture
def setup_db_2col_5audio_without_reddit(setup_tmpdir):
    return _setup_db_2col_5audio(setup_tmpdir, with_reddit=False)


def _setup_db_2col_5audio(tmpdir, with_reddit=True):
    sql_fn = os.path.join(
            TESTS_DIR, "all_test_files",
            f"db_2col_5audio{'without_reddit' if not with_reddit else ''}.sql")
    test_db_fn = os.path.join(tmpdir, "gwarip_db.sqlite")
    db_con, _ = load_or_create_sql_db(test_db_fn)

    with open(sql_fn, "r", encoding="UTF-8") as f:
        sql = f.read()

    db_con.executescript(sql)

    db_con.close()

    return tmpdir, test_db_fn


def test_set_missing_reddit(setup_tmpdir) -> None:
    return # TODO
    tmpdir, test_db_fn = setup_db_2col_5audio()

    db_con = sqlite3.connect(test_db_fn, detect_types=sqlite3.PARSE_DECLTYPES)
    c = db_con.execute("SELECT * FROM v_audio_and_collection_combined")
    original = c.fetchall()
    # TODO

    # artist inserted and arist_id of alias updated
    # inserted alias if it wasn't in db
    # redditinfo, filecol
    # AudioFile colid updated
    # selftext written
    fi = FileInfo(object, True, "m4a",
                  # only important that it has same url and author as one in db
                  "https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M",
                  "https://soundgasm.net/284291412sa324.m4a", None,
                  "AudiLEAVE_PRESENT_FIELDS_UNCHANGED [ASMR]",
                  "ThisLEAVE_PRESENT_FIELDS_UNCHANGEDion", "skitty")
    ri = RedditInfo(object, "reddit_url",
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
             None, None, None, None, None, "sassmastah77", "sassmastah77", None, None, 0],
            [2, "2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", "testy_user", None, None, 0],
            [3, "2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", "old_user", None, None, 0],
            ]

    query_str = "SELECT * FROM Downloads"

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    #
    #
    #

    fi.parent = ri
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(fi)

    expected[0][8:17] = [1254323.0, ri.r_post_url, ri.id, ri.title, ri.permalink,
                         ri.author, "sassmastah77", "sassmastah77", ri.subreddit]
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

    expected[1][8:17] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                         "26iw32o", ri.title, ri.permalink, ri.author,
                         "testy_user", "testy_user", ri.subreddit]

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
    expected[2][8:17] = [1602557093.0,
                         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
                         "2klj654", "don_t change this", ri.permalink, ri.author,
                         "old_user", "old_user", ri.subreddit]

    fn = ("No-filenäme_lo中al rem_veth_se_hehe ____ [let them stay] .this,too elongate "
          "elongate elongate elongate elongate.m4a.txt")
    # selftext written
    with open(os.path.join(tmpdir, "old_user", fn), 'r') as f:
        assert f.read() == ("Title: LEAVE_TITLE_FIELD_UNCHANGED\nPermalink: inserted_rddt3_url\n"
                            "Selftext:\n\nselfff3fffdszlbdftext")

    # reconnect so we make sure it's visible from diff connections
    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]


def test_add_to_db(setup_db_2col_5audio):

    tmpdir, test_db_fn = setup_db_2col_5audio

    query_str = """
    SELECT
        af.*,
        Alias.name as alias_name,
        Alias.artist_id as artist_id,
        Artist.id as artist_id,
        Artist.name as artist_name
    FROM AudioFile af
    JOIN Alias ON Alias.id = af.alias_id
    LEFT JOIN Artist ON Artist.id = Alias.artist_id
    {where_expression}
    """

    fi = FileInfo(object, True, "m4a", "https://soundgasm.net/testy_user/Best-title-SFW",
                  "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a", None,
                  "Best title [SFW]",
                  "This is another description", "alias_added_with_artist_id")
    ri = RedditInfo(object, "add/set_missing:should-use-r_post_url",
                    "26iw32o", "Best title on reddit [SFW]", "skitty-gwa",
                    "pillowtalkaudio", "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                    1602557093.0, [fi])
    fi.parent = ri

    # _add_to_db should NOT commit
    with GWARipper() as gwa:
        gwa._add_to_db(fi, 1, "generated [file] [name].mp3")

    # UNCHANGED!
    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE af.id > 6")) == []

    #
    #
    #
    expected = []

    expected.append(
            [7, 1, 1, time.strftime("%Y-%m-%d"), "This is another description",
             "generated [file] [name].mp3",
             "Best title [SFW]", "https://soundgasm.net/testy_user/Best-title-SFW",
             # 6 = alias_id which was added
             6, None, 0, 'alias_added_with_artist_id', 1, 1, 'skitty-gwa']
            )

    with GWARipper() as gwa:
        # collection_id set -> in db + downloaded_with_collection set
        # arist_id set on alias if info.reddit_info
        gwa._add_to_db(fi, 1, "generated [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE af.id > 6")) == [tuple(r) for r in expected]

    #
    # no artist_id if info.reddit_info.author is None
    #
    ri.author = None
    fi.page_url = 'adsflkjlasdlkdgflkadfsglkjafd;'
    fi.author = 'alias_with_ri_added_without_artist_id'

    with GWARipper() as gwa:
        gwa._add_to_db(fi, 2, "generated [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    expected.append(
            [8, 2, 1, time.strftime("%Y-%m-%d"), "This is another description",
             "generated [file] [name].mp3",
             "Best title [SFW]", fi.page_url,
             7, None, 0, fi.author, None, None, None]
            )

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE af.id > 6")) == [tuple(r) for r in expected]

    with GWARipper() as gwa:
        # reddit_info but no collection_id raises
        with pytest.raises(AssertionError):
            gwa._add_to_db(fi, None, "generated [file] [name].mp3")

    #
    # no reddit_info
    #
    fi.parent = None
    fi.page_url = 'asflkasdj32532'
    fi.author = 'alias_without_ri_added_without_artist_id'

    with GWARipper() as gwa:
        gwa._add_to_db(fi, None, "filename name ... [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    expected.append(
            [9, None, 0, time.strftime("%Y-%m-%d"), "This is another description",
             "filename name ... [file] [name].mp3",
             "Best title [SFW]", fi.page_url,
             8, None, 0, fi.author, None, None, None]
            )

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE af.id > 6")) == [tuple(r) for r in expected]

    #
    # uses already present alias
    #

    fi.parent = None
    fi.page_url = '3adslkfaslk34k'
    fi.author = 'sassmastah77'

    with GWARipper() as gwa:
        gwa._add_to_db(fi, None, "filename name ... [file] [name].mp3")
        gwa.db_con.commit()  # force commit

    expected.append(
            [10, None, 0, time.strftime("%Y-%m-%d"), "This is another description",
             "filename name ... [file] [name].mp3",
             "Best title [SFW]", fi.page_url,
             5, None, 0, fi.author, 2, 2, fi.author]
            )

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE af.id > 6")) == [tuple(r) for r in expected]


def test_add_to_db_ri(setup_db_2col_5audio):
    tmpdir, test_db_fn = setup_db_2col_5audio

    query_str = """
    SELECT
        fc.*,
        RedditInfo.created_utc,
        Alias.name as alias_name,
        Alias.artist_id as alias_artist_id,
        Artist.id as artist_id,
        Artist.name as artist_name
    FROM FileCollection fc
    LEFT JOIN RedditInfo ON RedditInfo.id = fc.reddit_info_id
    JOIN Alias ON Alias.id = fc.alias_id
    LEFT JOIN Artist ON Artist.id = Alias.artist_id
    {where_expression}
    """

    ri = RedditInfo(object, "add/set_missing:should-use-permalink",
                    "r3dd1t1d", "Best title on reddit [SFW]", "inserted-as-alias-and-artist",
                    "subr", "/r/subr/comments/r3dd1t1d/foo-bar-baz",
                    1602557093.0)

    #
    # _add_to_db_ri should not commit
    #
    with GWARipper() as gwa:
        assert gwa._add_to_db_ri(ri) == (3, ri.author)

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE fc.id > 2")) == []

    with GWARipper() as gwa:
        assert gwa._add_to_db_ri(ri) == (3, ri.author)
        gwa.db_con.commit()  # force commit

    expected = [
            [3, "https://www.reddit.com/r/subr/comments/r3dd1t1d/foo-bar-baz",
             #                            v-ri_id  v-alias_id
             ri.id, ri.title, ri.subpath, 3, None, 6, ri.created_utc, ri.author, 3, 3, ri.author]
    ]
    # artist inserted
    # alias inserted
    # alias using artist_id if ri.author
    # redditinfo inserted
    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE fc.id > 2")) == [tuple(r) for r in expected]

    #
    # ri with subpath
    #
    ri.nr_files = 4
    ri.permalink = 'sadflkjflkasdjlkfsadjlkj'
    # check if truncated title/subpath stored
    ri.title = "01234567890123456789012345678901234567890123456789012345678901234567890123456789"
    # re-use existing alias_id
    ri.author = 'sassmastah77'
    ri._update_subpath()

    expected.append(
        [4, 'https://www.reddit.com' + ri.permalink,
         #                subpath
         ri.id, ri.title, ri.title[:70], 4, None, 5, ri.created_utc, ri.author, 2, 2, ri.author]
    )
    with GWARipper() as gwa:
        assert gwa._add_to_db_ri(ri) == (4, ri.author)
        gwa.db_con.commit()  # force commit

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE fc.id > 2")) == [tuple(r) for r in expected]

    #
    # ri.author is None -> DELETED_USR_FOLDER
    #
    ri.nr_files = 2
    ri.permalink = 'flksadflkasjdlkkl'
    ri.title = "flkajsdlkl lkdslfkasl lksdflks"
    # use DELETED_USR_FOLDER
    ri.author = None
    ri._update_subpath()

    expected.append(
        [5, 'https://www.reddit.com' + ri.permalink,
         ri.id, ri.title, "", 5, None, 1, ri.created_utc,
         DELETED_USR_FOLDER, None, None, None]
    )
    with GWARipper() as gwa:
        assert gwa._add_to_db_ri(ri) == (5, DELETED_USR_FOLDER)
        gwa.db_con.commit()  # force commit

    assert get_all_rowtuples_db(
            test_db_fn,
            query_str.format(where_expression="WHERE fc.id > 2")) == [tuple(r) for r in expected]


def test_already_downloaded(monkeypatch, setup_db_2col_5audio):
    tmpdir, test_db_fn = setup_db_2col_5audio
    cfg.config["Settings"]["set_missing_reddit"] = "False"

    db_con = sqlite3.connect(test_db_fn, detect_types=sqlite3.PARSE_DECLTYPES)

    fi1 = FileInfo(object, True, "m4a",
                   "https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M",
                   *([None] * 5))

    db_con.execute("UPDATE AudioFile SET url = ? WHERE id = 2",
                   ('direct_url_used_for_already_downloaded',))
    fi2 = FileInfo(object, True, "m4a", None,  # url none
                   # both url and direct_url should be used for checking in db
                   'direct_url_used_for_already_downloaded',
                   *([None] * 4))

    fi3 = FileInfo(object, True, "m4a", 'blakjlaskd',  # url not in db
                   # both url and direct_url should be used for checking in db
                   'direct_url_used_for_already_downloaded',
                   *([None] * 4))

    fi4 = FileInfo(object, True, "m4a",
                   "https://soundgasm.net/u/skitty/Not-Downloaded",
                   *([None] * 5))
    fi5 = FileInfo(object, True, "m4a",
                   "https://chirb.it/2jkr532k",
                   *([None] * 5))

    db_con.commit()

    # nothing should happen
    with GWARipper() as gwa:
        assert gwa.already_downloaded(fi1) is True
        assert fi1.already_downloaded is True

        assert gwa.already_downloaded(fi2) is True
        assert fi2.already_downloaded is True

        assert gwa.already_downloaded(fi3) is True
        assert fi3.already_downloaded is True

        assert gwa.already_downloaded(fi4) is False
        assert fi4.already_downloaded is False

        assert gwa.already_downloaded(fi5) is False
        assert fi5.already_downloaded is False

    #
    # check if set_missing_reddit is called correctly
    #
    ri = RedditInfo(*([None] * 8))
    fi1.parent = ri

    called_with_audio_id = None
    called_with_info = None

    def patched_set_missing(self, audio_id, info):
        nonlocal called_with_audio_id
        nonlocal called_with_info
        called_with_audio_id = audio_id
        called_with_info = info

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.set_missing_reddit_db',
                        patched_set_missing)

    with GWARipper() as gwa:
        gwa.already_downloaded(fi1)
    assert called_with_audio_id is None
    assert called_with_info is None

    cfg.config["Settings"]["set_missing_reddit"] = "True"

    # don't call if collection_id is set
    with GWARipper() as gwa:
        gwa.already_downloaded(fi1)
    assert called_with_audio_id is None
    assert called_with_info is None

    # set collection_id to NULL
    db_con.execute("UPDATE AudioFile SET collection_id = NULL WHERE id = 1")
    db_con.commit()
    db_con.close()

    with GWARipper() as gwa:
        gwa.already_downloaded(fi1)
    assert called_with_audio_id == 1
    assert called_with_info is fi1


# split in downloa_file /download_collection
def test_download(setup_tmpdir, monkeypatch, caplog):
    return  # TODO
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
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, author_page,
        author_subdir, subreddit_name
        )
    VALUES
        ("2020-01-23", "13:37", "This is a description", "audio_file.m4a",
         "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
         "https://soundgasm.net/sassmastah77/Audio-title-ASMR", NULL,
         NULL, NULL, NULL, NULL, NULL, "sassmastah77", "sassmastah77", NULL),

        ("2020-12-13", "13:37", "This is another description", "subpath\\super_file.mp3",
         "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
         "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
         "26iw32o", NULL, NULL, NULL, "testy_user", "testy_user", NULL),

        ("2020-12-15", "15:37", "asdlkgjadslkg lkfdgjdslkgjslkd", NULL,
         "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate elongate elongate elongate elongate elongate elongate",
         "https://no-page-url.com/324q523q.mp3", NULL, 1602557093.0,
         "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
         "2klj654", "don_t change this", NULL, NULL, "old_user", "old_user", NULL);

    COMMIT;
    """)

    expected = [
            [1, "2020-01-23", "This is a description", "audio_file.m4a",
             "Audio title [ASMR]", "https://soundgasm.net/284291412sa324.m4a",
             "https://soundgasm.net/sassmastah77/Audio-title-ASMR", None,
             None, None, None, None, None, "sassmastah77", "sassmastah77", None, None, 0],
            [2, "2020-12-13", "This is another description", "subpath\\super_file.mp3",
             "Best title [SFW]", "https://soundgsgasgagasm.net/28429SGSAG24sa324.m4a",
             "https://soundgasm.net/testy_user/Best-title-SFW", 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
             "26iw32o", None, None, None, "testy_user", "testy_user", None, None, 0],
            [3, "2020-12-15", "asdlkgjadslkg lkfdgjdslkgjslkd", None,
             "No-filenäme_lo中al rem\\veth:se/hehe 🍕🥟🧨❤ [let them stay] .this,too elongate "
             "elongate elongate elongate elongate elongate elongate",
             "https://no-page-url.com/324q523q.mp3", None, 1602557093.0,
             "https://www.reddit.com/r/pillowtalkaudio/comments/2klj654/salfl-slaf-asfl",
             "2klj654", "don_t change this", None, None, "old_user", "old_user", None, None, 0],
            ]

    # everything but time col
    query_str = """SELECT
        id, date, description, local_filename, title, url_file, url, created_utc,
        r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, author_page,
        author_subdir, subreddit_name, rating, favorite FROM Downloads"""

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
    fi0_rep = ExtractorReport(fi0.page_url, ExtractorErrorCode.NO_ERRORS)
    fi0.report = fi0_rep

    # non audio file should not be added to db - only downloaded
    with GWARipper() as gwa:
        gwa.download(fi0)
        assert fi0.downloaded is True
        assert fi0.report.downloaded is True

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
    fi1_rep = ExtractorReport(fi1.page_url, ExtractorErrorCode.NO_ERRORS)
    fi1.report = fi1_rep

    # testing file has already_downloaded set
    assert fi1.downloaded is False
    with GWARipper() as gwa:
        gwa.download(fi1)
        assert fi1.downloaded is False
        assert fi1.report.downloaded is False

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
             None, None, fi1.author, fi1.author, None, None, 0]
            )

    with GWARipper() as gwa:
        gwa.download(fi1)
        assert fi1.downloaded is True
        assert fi1.report.downloaded is True

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
    fi2_rep = ExtractorReport(fi2.page_url, ExtractorErrorCode.NO_ERRORS)
    fi2.report = fi2_rep
    fi2_fn = f"01_{fi2.title}.{fi2.ext}"
    fi3 = FileInfo(object, True, "mp3", "https://page.url/242lk2598242jrtn3l4",
                   build_file_url(os.path.join(testdl_files, "fi3")), None,  # id
                   "[Foo] Bar qux ❤",  # title
                   rnd.random_string(50), "other-than_rddt-usr")
    fi3_rep = ExtractorReport(fi3.page_url, ExtractorErrorCode.NO_ERRORS)
    fi3.report = fi3_rep
    fi3_fn = f"Prepended title_01_[Foo] Bar qux _.{fi3.ext}"
    # extr, url, id
    fc1 = FileCollection(object, rnd.random_string(30), rnd.random_string(7),
                         "Prepended title", "other-than_rddt-usr2",
                         [fi3])
    fc1_rep = ExtractorReport(fc1.url, ExtractorErrorCode.NO_ERRORS)
    fc1.report = fc1_rep
    fi4 = FileInfo(object, False, "gif", "https://page.url/245j2l56t2098432",
                   build_file_url(os.path.join(testdl_files, "fi4")), rnd.random_string(5),  # id
                   "non-audio_file",  # title
                   None, "other-than_rddt-usr3")
    fi4_rep = ExtractorReport(fi4.page_url, ExtractorErrorCode.NO_ERRORS)
    fi4.report = fi4_rep
    fi4_fn = f"02_{fi4.title}.{fi4.ext}"
    ri1 = RedditInfo(object, "https://dont-use-this-url/in-db",
                     rnd.random_string(6), "Reddit:title / as sub\\path", "reddit_user",
                     rnd.random_string(15), "/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz",
                     1602557093.0, [fi2, fc1, fi4])
    ri1.selftext = "selftext_should not have been written"
    ri1.r_post_url = "https://www.reddit.com/r/pillowtalkaudio/comments/26iw32o/foo-bar-baz"
    ri1_rep = ExtractorReport(ri1.url, ExtractorErrorCode.NO_ERRORS)
    ri1.report = ri1_rep
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
    # all downloaded or already_downloaded children means collection is also downloaded
    assert ri1.downloaded is True
    assert ri1.report.downloaded is True

    # report.downloaded set on children
    assert fc1.downloaded is True

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
    ri1.downloaded = False
    fc1.downloaded = False
    # reset already downloaded
    fi2.already_downloaded = False
    fi3.already_downloaded = False
    fi4.already_downloaded = False

    ri1_dirname = os.path.join("Reddit_title _ as sub_path")
    expected.extend([
            [5, time.strftime("%Y-%m-%d"), fi2.descr, os.path.join(ri1_dirname, fi2_fn),
             fi2.title, fi2.direct_url, fi2.page_url, ri1.created_utc, ri1.r_post_url,
             ri1.id, ri1.title, ri1.permalink,  ri1.author, fi2.author, ri1.author,
             ri1.subreddit, None, 0],
            [6, time.strftime("%Y-%m-%d"), fi3.descr, os.path.join(ri1_dirname, fi3_fn),
             fi3.title, fi3.direct_url, fi3.page_url, ri1.created_utc, ri1.r_post_url,
             ri1.id, ri1.title, ri1.permalink,  ri1.author, fi3.author, ri1.author,
             ri1.subreddit, None, 0],
            ])

    with GWARipper() as gwa:
        gwa.download(ri1)
    assert ri1.downloaded is True
    # also set on children _collections_
    assert fc1.downloaded is True

    assert fi2.downloaded
    assert fi3.downloaded
    assert fi4.downloaded

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    # selftext
    ri1_dir_abs = os.path.join(tmpdir, ri1.author, ri1_dirname)
    with open(os.path.join(ri1_dir_abs, "Reddit_title _ as sub_path.txt"), "r") as f:
        assert f.read() == (
                f"Title: {ri1.title}\nPermalink: {ri1.permalink}\nSelftext:\n\n{ri1.selftext}")
    fns = [None, fi1_fn, fi2_fn, fi3_fn, fi4_fn]
    for i in range(2, 5):
        with open(os.path.join(ri1_dir_abs, fns[i]), "r") as f:
            assert f.read() == fi_file_contents[i]

    #
    # fcol download with one failed dl
    #
    # reuse fi4 since it wasn't added to db but with diff parent
    fi4.downloaded = False
    fi4.is_audio = True
    fi4.ext = "wav"
    fi4_fn = f"FC2 _ Prep_ended ti_tle_01_{fi4.title}.{fi4.ext}"

    fi5 = FileInfo(SoundgasmExtractor, False, "gif", "https://page.url/asjfgl3oi5j23",
                   build_file_url(os.path.join(testdl_files, "fi5")), rnd.random_string(5),  # id
                   "should raise",  # title
                   None, "exceptional")
    # extr, url, id
    fc2 = FileCollection(object, rnd.random_string(30), rnd.random_string(7),
                         "FC2 ? Prep/ended ti:tle", "fcol_author",
                         [fi4, fi5])
    fi4.parent = fc2
    fi5.parent = fc2

    expected.append(
            [7, time.strftime("%Y-%m-%d"), fi4.descr, fi4_fn,
             fi4.title, fi4.direct_url, fi4.page_url, None, None,
             None, None, None,  None, fi4.author, fc2.author, None, None, 0]
            )

    assert fi4.reddit_info is None  # just to be sure
    assert fi5.reddit_info is None  # just to be sure

    with GWARipper() as gwa:
        gwa.download(fc2)
    # not all children could be downloaded
    assert fc2.downloaded is False

    assert fi4.downloaded

    assert get_all_rowtuples_db(test_db, query_str) == [tuple(r) for r in expected]

    fc2_dir = os.path.join(tmpdir, fc2.author)
    with open(os.path.join(fc2_dir, fi4_fn), "r") as f:
        assert f.read() == fi_file_contents[4]

    # reset parent
    fi5.parent = None

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
        fi.update_downloaded()  # normally called by _download_collection

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    redditinfo = RedditInfo(RedditExtractor, "url", "id", "title",
                            'author', 'subreddit', 'permalink', 12345.0)
    redditinfo_permalink = redditinfo.permalink
    redditinforep = ExtractorReport(redditinfo.url, ExtractorErrorCode.NO_ERRORS)
    redditinfo.report = redditinforep  # so downloaded gets propagted to report
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

    # context manager writes reports on exit so use without it here
    g = GWARipper()
    g.write_report(reports)

    expected_str = "\n".join(expected)
    with open(
            os.path.join(tmpdir, "_reports",
                         f"report_{time.strftime('%Y-%m-%dT%Hh%Mm')}.html"),
            "r") as f:
        assert expected_str == f.read()
