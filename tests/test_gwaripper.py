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
from gwaripper.info import FileInfo, RedditInfo, FileCollection, DELETED_USR_FOLDER, UNKNOWN_USR_FOLDER
from gwaripper.download import DownloadErrorCode
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

    reports = [(ExtractorReport('url', ExtractorErrorCode.NO_EXTRACTOR), DownloadErrorCode.NOT_DOWNLOADED)]

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
            f"db_2col_5audio{'_without_reddit' if not with_reddit else ''}.sql")
    test_db_fn = os.path.join(tmpdir, "gwarip_db.sqlite")
    db_con, _ = load_or_create_sql_db(test_db_fn)

    with open(sql_fn, "r", encoding="UTF-8") as f:
        sql = f.read()

    db_con.executescript(sql)

    db_con.close()

    return tmpdir, test_db_fn


def test_set_missing_reddit(setup_db_2col_5audio_without_reddit) -> None:
    tmpdir, test_db_fn = setup_db_2col_5audio_without_reddit

    query_str = """
    SELECT
        AudioFile.*,
        Alias.name as alias_name,
        Alias.artist_id as alias_artist_id,
        Artist.name as artist_name,
        FileCollection.id as fcol_id,
        FileCollection.url as fcol_url,
        FileCollection.id_on_page as fcol_id_on_page,
        FileCollection.title as fcol_title,
        FileCollection.subpath as fcol_subpath,
        FileCollection.reddit_info_id as fcol_reddit_info_id,
        FileCollection.parent_id as fcol_parent_id,
        FileCollection.alias_id as fcol_alias_id,
        (SELECT
                Alias.name
         FROM Alias WHERE Alias.id = FileCollection.alias_id) as fcol_alias_name,
        RedditInfo.created_utc as reddit_created_utc
    FROM AudioFile
    LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
    LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
    JOIN Alias ON Alias.id = AudioFile.alias_id
    LEFT JOIN Artist ON Artist.id = Alias.artist_id
    {where_expression}"""

    fi = FileInfo(object, True, "m4a",
                  # only important that it has same url and author as one in db
                  "https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M",
                  "https://soundgasm.net/284291412sa324.m4a", None,
                  "AudiLEAVE_PRESENT_FIELDS_UNCHANGED [ASMR]",
                  "ThisLEAVE_PRESENT_FIELDS_UNCHANGEDion", "skitty")
    ri = RedditInfo(object, "reddit_url",
                    #                                              v use this as artist
                    "inserted_reddit_id", "isnerted_reddit_title", "sassmastah77",
                    "inserted/subreddit", 'inserted_rddt_url', 1254323.0, children=[fi])
    ri.nr_files = 4
    ri.selftext = "selftext not written to subpath even though ri has subpath"
    ri.r_post_url = "url-to-self-or-outgoing"
    fi.parent = ri

    expected = [
        # id, col_id, downloaded_with_collection, date
        (1, 1, 0, '2020-11-13',
         # descr
         '[F4M] [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breast play] '
         '[Outercourse] [Handjob] [Cozy blanket] [Kissing] [Thighjob] [Pinning you '
         'down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [Script: BowTieGuy]',
         # filename
         '02_Motherly Moth Girl Keeps You Warm [F4M].m4a',
         # title
         'Motherly Moth Girl Keeps You Warm [F4M]',
         # url
         'https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M',
         # alias_id, rating, fav
         4, None, 0,
         # alias_name, alias_artist_id, artist_name
         'skitty', 1, 'sassmastah77',
         # fcol_id
         1,
         # fcol_url
         'https://www.reddit.cominserted_rddt_url',
         # fcol_id_on_page, fcol_title,
         'inserted_reddit_id', 'isnerted_reddit_title',
         # fcol_subpath
         'isnerted_reddit_title',
         # fcol_reddit_info_id, fcol_parent_id, fcol_alias_id, fcol_alias_name
         1, None, 5, 'sassmastah77',
         # created_utc
         1254323.0)
    ]

    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(1, fi)

    # artist inserted (technically part of _add_to_db_ri) and arist_id of alias updated
    # redditinfo, filecol
    # AudioFile colid updated
    assert get_all_rowtuples_db(
        test_db_fn,
        query_str.format(where_expression="WHERE collection_id IS NOT NULL")
    ) == [tuple(r) for r in expected]

    # selftext written
    # under alias_name of AudioFile _without_ subpath since it was
    # obv. not downloade as part of an collection
    with open(os.path.join(tmpdir, "skitty",
                           # AudioFile.filename
                           expected[0][5] + ".txt"), "r") as f:
        assert f.read() == (f"Title: {ri.title}\nPermalink: {ri.permalink}\n"
                            f"Selftext:\n\n{ri.selftext}")

    #
    # artist_id should not be updated if it's not NULL
    #
    ri.author = 'sdaflksjdl'  # will still be inserted
    ri.permalink = 'asdfjlaksfsdlfls'
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(1, fi)

    # artist_id should not be updated if it's not NULL
    assert get_all_rowtuples_db(
        test_db_fn,
        """
        SELECT Alias.artist_id, Artist.name
        FROM Alias
        LEFT JOIN Artist ON Artist.id = Alias.artist_id
        WHERE Alias.id = 4"""
    ) == [(1, 'sassmastah77')]


def test_set_missing_reddit_no_filenme(
        setup_db_2col_5audio_without_reddit,
        monkeypatch):
    # only testing selftext written from re-computed filename
    tmpdir, test_db_fn = setup_db_2col_5audio_without_reddit

    fi = FileInfo(object, True, "m4a",
                  # only important that it has same url and author as one in db
                  "https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M",
                  "https://soundgasm.net/284291412sa324.m4a", None,
                  "AudiLEAVE_PRESENT_FIELDS_UNCHANGED [ASMR]",
                  "ThisLEAVE_PRESENT_FIELDS_UNCHANGEDion", "skitty")
    ri = RedditInfo(object, "reddit_url",
                    #                                              v use this as artist
                    "inserted_reddit_id", "isnerted_reddit_title", "sassmastah77",
                    "inserted/subreddit", 'inserted_rddt_url', 1254323.0, children=[fi])
    ri.nr_files = 4
    ri.selftext = "selftext written to re-computed filename"
    ri.r_post_url = "url-to-self-or-outgoing"
    fi.parent = ri

    title = (
        "[F4M] [Gentle Fdom] [Size difference] [Thicc] !@#:<M>)((❤💋 [Breast play]"
        " [Outercourse] [Handjob] [Cozy blanket] [Kissing] [Thighjob] [Pinning you "
        "down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [Script: BowTieGuy]"
    )
    db_con = sqlite3.connect(test_db_fn, detect_types=sqlite3.PARSE_DECLTYPES)
    db_con.execute("UPDATE AudioFile SET filename = ?, title = ? WHERE id = ?",
                   ("", title, 1))
    db_con.commit()
    db_con.close()

    fn = (
        "[F4M] [Gentle Fdom] [Size difference] [Thicc] _____M______ [Breast play]"
        " [Outercourse] [Handjob] [Cozy blanket.m4a.txt"
    )
    with GWARipper() as gwa:
        gwa.set_missing_reddit_db(1, fi)

    # re-computed filename from title if filename missing
    with open(os.path.join(tmpdir, "skitty", fn), "r") as f:
        assert f.read() == (f"Title: {ri.title}\nPermalink: {ri.permalink}\n"
                            f"Selftext:\n\n{ri.selftext}")


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
    # inserting a FileCollection whose url is already in the db
    # returns that FileCollection's id and
    #
    ri.author = 'asdlkfjsal'  # return artist_name of existing fcol in DB
    with GWARipper() as gwa:
        assert gwa._add_to_db_ri(ri) == (3, 'inserted-as-alias-and-artist')
        gwa.db_con.commit()  # force commit
    # nothing changed
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
        assert fi1.downloaded is DownloadErrorCode.SKIPPED_DUPLICATE

        assert gwa.already_downloaded(fi2) is True
        assert fi2.downloaded is DownloadErrorCode.SKIPPED_DUPLICATE

        assert gwa.already_downloaded(fi3) is True
        assert fi3.downloaded is DownloadErrorCode.SKIPPED_DUPLICATE

        assert gwa.already_downloaded(fi4) is False
        assert fi4.downloaded is DownloadErrorCode.NOT_DOWNLOADED

        assert gwa.already_downloaded(fi5) is False
        assert fi5.downloaded is DownloadErrorCode.NOT_DOWNLOADED

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


def test_download_file(monkeypatch, caplog, setup_db_2col_5audio):
    tmpdir, test_db_fn = setup_db_2col_5audio

    called_with = {}

    class DummyCon:
        def __enter__(self):
            called_with['db_con__enter__'] = True

        def __exit__(self, *args, **kwargs):
            # just important that it was called
            called_with['db_con__exit__'] = True

    already_downloaded = True

    def patched_already_downloaded(self, *args, **kwargs):
        called_with['already_downloaded'] = (args, kwargs)
        if already_downloaded:
            args[0].downloaded = DownloadErrorCode.SKIPPED_DUPLICATE
        return already_downloaded

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper.already_downloaded",
                        patched_already_downloaded)

    generate_filename_ret = ("subpath_test", "fi_ena_e", "txt")

    def patched_generate_filename(self, *args, **kwargs):
        called_with['generate_filename'] = (args, kwargs)
        return generate_filename_ret

    monkeypatch.setattr("gwaripper.info.FileInfo.generate_filename",
                        patched_generate_filename)

    pad_filename_ret = "fi_ena_e_02"

    def patched_pad_filename(self, *args, **kwargs):
        called_with['pad_filename'] = (args, kwargs)
        return pad_filename_ret

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._pad_filename_if_exists",
                        patched_pad_filename)

    ret_id_in_db = 99

    def patched_add_to_db(self, *args, **kwargs):
        called_with['add_to_db'] = (args, kwargs)
        return ret_id_in_db

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._add_to_db",
                        patched_add_to_db)

    download_sould_raise = None

    def patched_download_in_chunks(*args, **kwargs):
        called_with['download_in_chunks'] = (args, kwargs)
        if download_sould_raise is not None:
            raise download_sould_raise

    monkeypatch.setattr("gwaripper.download.download_in_chunks",
                        patched_download_in_chunks)

    fi = FileInfo(object, True, "jpg", "https://page.url/al3234653",
                  "direct_url", None,  # id
                  "dont_overwrite",  # title
                  "This is the description fi0", "page_user")

    caplog.set_level(logging.INFO)

    # already downloaded file
    gwa = GWARipper()
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=0, dl_idx=3, dl_max=5) is None
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.SKIPPED_DUPLICATE

    assert called_with == {
        'already_downloaded': ((fi,), {}),
    }
    assert f"File was already downloaded, skipped URL: {fi.page_url}" == (
            caplog.records[0].message)

    called_with.clear()
    caplog.clear()
    fi.id_in_db = None

    #
    # normal audio download
    #

    already_downloaded = False

    gwa = GWARipper()
    gwa.db_con = DummyCon()
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=3, dl_max=5) == generate_filename_ret[0]
    assert fi.id_in_db == ret_id_in_db
    assert fi.downloaded is DownloadErrorCode.DOWNLOADED

    abs_subpath = os.path.join(tmpdir, 'author_name', generate_filename_ret[0])
    fn = f"{pad_filename_ret}.{generate_filename_ret[2]}"
    # check dirs created
    assert os.path.isdir(abs_subpath)

    assert called_with == {
        'already_downloaded': ((fi,), {}),
        'generate_filename': ((None, 2), {}),
        'pad_filename': (
            (abs_subpath, generate_filename_ret[1], generate_filename_ret[2]), {}),
        # is_audio -> using context manager to commit or rollback
        'db_con__enter__': True,
        'db_con__exit__': True,
        'add_to_db': ((fi, None, fn), {}),
        'download_in_chunks': (
            (fi.direct_url, os.path.join(abs_subpath, fn)), {'prog_bar': True}),
    }

    # download logging call using dl_idx and dl_max
    assert f"Downloading: {fn}..., File 3 of 5" == (caplog.records[0].message)

    fi.downloaded = DownloadErrorCode.NOT_DOWNLOADED
    fi.id_in_db = None
    called_with.clear()
    caplog.clear()

    #
    # non-audio does not commit to db
    #
    fi.is_audio = False
    gwa = GWARipper()
    gwa.db_con = DummyCon()
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.DOWNLOADED

    abs_subpath = os.path.join(tmpdir, 'author_name', generate_filename_ret[0])
    fn = f"{pad_filename_ret}.{generate_filename_ret[2]}"
    # check dirs created
    assert os.path.isdir(abs_subpath)

    # is_audio False -> not using context manager
    assert called_with == {
        'already_downloaded': ((fi,), {}),
        'generate_filename': ((None, 2), {}),
        'pad_filename': (
            (abs_subpath, generate_filename_ret[1], generate_filename_ret[2]), {}),
        'download_in_chunks': (
            (fi.direct_url, os.path.join(abs_subpath, fn)), {'prog_bar': True}),
    }

    # download logging call using dl_idx and dl_max
    assert f"Downloading: {fn}..., File 7 of 120" == (caplog.records[0].message)

    fi.is_audio = True
    fi.id_in_db = None
    fi.downloaded = DownloadErrorCode.NOT_DOWNLOADED
    called_with.clear()
    caplog.clear()

    #
    # no author name -> UNKNOWN_USR_FOLDER
    #
    gwa = GWARipper()
    gwa.db_con = DummyCon()
    assert gwa._download_file(fi, author_name=None, top_collection=None,
                              file_index=2, dl_idx=3, dl_max=5) == generate_filename_ret[0]
    assert fi.id_in_db == ret_id_in_db
    assert fi.downloaded is DownloadErrorCode.DOWNLOADED

    abs_subpath = os.path.join(tmpdir, UNKNOWN_USR_FOLDER, generate_filename_ret[0])
    fn = f"{pad_filename_ret}.{generate_filename_ret[2]}"
    # check dirs created
    assert os.path.isdir(abs_subpath)

    assert called_with == {
        'already_downloaded': ((fi,), {}),
        'generate_filename': ((None, 2), {}),
        'pad_filename': (
            (abs_subpath, generate_filename_ret[1], generate_filename_ret[2]), {}),
        # is_audio -> using context manager to commit or rollback
        'db_con__enter__': True,
        'db_con__exit__': True,
        'add_to_db': ((fi, None, fn), {}),
        'download_in_chunks': (
            (fi.direct_url, os.path.join(abs_subpath, fn)), {'prog_bar': True}),
    }

    # download logging call using dl_idx and dl_max
    assert f"Downloading: {fn}..., File 3 of 5" == (caplog.records[0].message)

    fi.downloaded = DownloadErrorCode.NOT_DOWNLOADED
    fi.id_in_db = None
    called_with.clear()
    caplog.clear()

    #
    # except HTTPError, ContentTooShortError, URLError
    #

    # DOES NOT WORK
    # caplog.set_level(logging.WARNING)

    abs_subpath = os.path.join(tmpdir, 'author_name', generate_filename_ret[0])
    fn = f"{pad_filename_ret}.{generate_filename_ret[2]}"
    exc_tests_called_with = {
        'already_downloaded': ((fi,), {}),
        'generate_filename': ((None, 2), {}),
        'pad_filename': (
            (abs_subpath, generate_filename_ret[1], generate_filename_ret[2]), {}),
        # is_audio -> using context manager to commit or rollback
        'db_con__enter__': True,
        'db_con__exit__': True,
        'add_to_db': ((fi, None, fn), {}),
        'download_in_chunks': (
            (fi.direct_url, os.path.join(abs_subpath, fn)), {'prog_bar': True}),
    }

    #
    # HTTPError
    #
    download_sould_raise = urllib.error.HTTPError(
            fi.direct_url, 404, "Not Found", {}, None)
    gwa = GWARipper()
    gwa.db_con = DummyCon()
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.HTTP_ERR_NOT_FOUND

    assert called_with == exc_tests_called_with

    assert caplog.records[1].message == (f"HTTP Error 404: Not Found: \"{fi.direct_url}\"")

    called_with.clear()
    caplog.clear()
    fi.id_in_db = None
    # TODO this is so bad: use a fixture and sep functions or parametrize
    fi.downloaded = DownloadErrorCode.NOT_DOWNLOADED

    #
    # ContentTooShortError
    #
    download_sould_raise = urllib.error.ContentTooShortError("Content too short!", None)
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    assert called_with == exc_tests_called_with

    assert caplog.records[1].message == ("Content too short!")
    assert "File information was not added to DB!" in caplog.records[2].message

    called_with.clear()
    caplog.clear()
    fi.id_in_db = None

    #
    # ContentTooShortError WITH fc parent
    #
    fc = FileCollection(None, "fc_url", *([None] * 3))
    fi.parent = fc
    download_sould_raise = urllib.error.ContentTooShortError("Content too short!", None)
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    assert called_with == exc_tests_called_with

    assert caplog.records[1].message == ("Content too short!")
    assert "File information was not added to DB!" in caplog.records[2].message
    assert caplog.records[3].message == (f"Containing root collection: {fc.url}")

    called_with.clear()
    caplog.clear()
    fi.id_in_db = None

    #
    # ContentTooShortError WITH ri parent
    #
    ri = RedditInfo(None, "fc_url", *([None] * 6))
    fi.parent = ri
    download_sould_raise = urllib.error.ContentTooShortError("Content too short!", None)
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    assert called_with == exc_tests_called_with

    assert caplog.records[1].message == ("Content too short!")
    assert "File information was not added to DB!" in caplog.records[2].message
    assert caplog.records[3].message == (f"Containing root collection: {ri.url}")

    called_with.clear()
    caplog.clear()
    fi.id_in_db = None

    #
    # URLError
    #
    fi.parent = None
    fi.extractor = SoundgasmExtractor
    download_sould_raise = urllib.error.URLError("Reason for error!")
    assert gwa._download_file(fi, author_name='author_name', top_collection=None,
                              file_index=2, dl_idx=7, dl_max=120) == generate_filename_ret[0]
    assert fi.id_in_db is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    assert called_with == exc_tests_called_with

    assert (f"URL Error for {fi.direct_url}: Reason for error!\nExtractor "
            f"{fi.extractor} is probably broken!") in caplog.records[1].message


def test_download_collection(monkeypatch, caplog, setup_db_2col_5audio):
    tmpdir, test_db_fn = setup_db_2col_5audio

    called_with = {'download_file': []}

    preferred_author_ret = "pref_auth"

    def patched_get_preferred_author(self, *args, **kwargs):
        called_with['preferred_author'] = (args, kwargs)
        return preferred_author_ret

    monkeypatch.setattr("gwaripper.info.FileCollection.get_preferred_author_name",
                        patched_get_preferred_author)

    id_in_db = 11
    add_to_db_col_ret = ('redd_auth', False)

    def patched_add_to_db_col(self, col, author, **kwargs):
        called_with['add_to_db_col'] = ((col, author), kwargs)
        col.id_in_db = id_in_db
        return add_to_db_col_ret

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._add_to_db_collection",
                        patched_add_to_db_col)

    add_to_db_ri_ret = (id_in_db, 'redd_auth')

    def patched_add_to_db_ri(self, *args, **kwargs):
        called_with['add_to_db_ri'] = (args, kwargs)
        return add_to_db_ri_ret

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._add_to_db_ri",
                        patched_add_to_db_ri)

    set_downloaded = set()

    def patched_download_file(self, info, auth, top_col, fi_idx, dl_idx, *args, **kwargs):
        called_with['download_file'].append(((info, auth, top_col, fi_idx, dl_idx) + args, kwargs))
        info.downloaded = (
            DownloadErrorCode.DOWNLOADED if info in set_downloaded else DownloadErrorCode.NOT_DOWNLOADED)

    monkeypatch.setattr("gwaripper.gwaripper.GWARipper._download_file",
                        patched_download_file)

    class DummyCon:
        lastrowid = id_in_db

        def rollback(self):
            called_with['db_con_rollback'] = True

        def cursor(self):
            return self

        def execute(self, *args, **kwargs):
            return self

        def fetchone(self):
            return dict()
        
        def __enter__(*args):
            pass

        def __exit__(*args):
            pass


    generate_filename_ret = ("subpath_test", "fi_ena_e", "txt")

    def patched_generate_filename(self, *args, **kwargs):
        called_with['generate_filename'] = (args, kwargs)
        return generate_filename_ret

    monkeypatch.setattr("gwaripper.info.FileInfo.generate_filename",
                        patched_generate_filename)

    def patched_write_selftext(self, *args, **kwargs):
        called_with['write_selftext'] = (args, kwargs)

    monkeypatch.setattr("gwaripper.info.RedditInfo.write_selftext_file",
                        patched_write_selftext)

    #
    # also add fcol to db (not just reddit info)
    #

    fi1 = FileInfo(None, True, *([None] * 7))
    fc1 = FileCollection(None, 'fcol_url', *([None] * 3))
    fc1.add_file(fi1)

    set_downloaded = {fi1}

    gwa = GWARipper()
    gwa.db_con = DummyCon()
    gwa._download_collection(fc1, None)

    assert fi1.downloaded is DownloadErrorCode.DOWNLOADED
    assert fc1.downloaded is DownloadErrorCode.COLLECTION_COMPLETE

    # checking the whole dict equals .. better than just checking specific items
    # or using ... in called_with
    assert called_with == {
        'add_to_db_col': ((fc1, preferred_author_ret), {}),
        # no file_idx passed if only one file
        'download_file': [
            ((fi1, preferred_author_ret, fc1, 0, 1), {'dl_max': 1})
        ],
        'preferred_author': ((), {}),
    }

    called_with.clear()
    called_with['download_file'] = []
    caplog.clear()

    #
    # log and rollback if no audio downloads
    # + file_idx passed to download_file if > 1 file
    #
    fi1 = FileInfo(None, False, *([None] * 7))
    fi2 = FileInfo(None, True, *([None] * 7))
    ri = RedditInfo(None, 'reddit_url', *([None] * 6))
    ri.add_file(fi1)
    ri.add_file(fi2)

    # non audio will be downloaded, audio not -> any_audio_downloads = False
    set_downloaded = {fi1}

    gwa = GWARipper()
    gwa.db_con = DummyCon()
    gwa._download_collection(ri, None)

    assert ri.downloaded is DownloadErrorCode.COLLECTION_INCOMPLETE

    assert fi1.downloaded is DownloadErrorCode.DOWNLOADED
    # downloaded on _only_ audio is False so db will get rolled back
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    assert called_with == {
        # file_idx passed if more than one file
        'download_file': [
            ((fi1, preferred_author_ret, ri, 1, 1), {'dl_max': 2}),
            ((fi2, preferred_author_ret, ri, 2, 2), {'dl_max': 2})
        ],
        'preferred_author': ((), {}),
    }

    called_with.clear()
    called_with['download_file'] = []
    caplog.clear()

    #
    # complete collection downloaded
    #
    fi1 = FileInfo(None, False, *([None] * 7))
    fi2 = FileInfo(None, True, *([None] * 7))
    ri = RedditInfo(None, 'reddit_url', *([None] * 6))
    ri.add_file(fi1)
    ri.add_file(fi2)

    set_downloaded = {fi1, fi2}

    gwa = GWARipper()
    gwa.db_con = DummyCon()
    gwa._download_collection(ri, None)

    assert ri.downloaded is DownloadErrorCode.COLLECTION_COMPLETE

    assert fi1.downloaded is DownloadErrorCode.DOWNLOADED
    assert fi2.downloaded is DownloadErrorCode.DOWNLOADED

    assert called_with == {
        'add_to_db_ri': ((ri,), {}),
        # file_idx passed if more than one file
        'download_file': [
            ((fi1, preferred_author_ret, ri, 1, 1), {'dl_max': 2}),
            ((fi2, preferred_author_ret, ri, 2, 2), {'dl_max': 2})
        ],
        'preferred_author': ((), {}),
        'write_selftext': (
            (cfg.get_root(), os.path.join(preferred_author_ret, "")), {})
    }

    called_with.clear()
    called_with['download_file'] = []
    caplog.clear()

    #
    # normal ri download
    # + write selftext
    #

    fi1 = FileInfo(None, False, *([None] * 7))
    fi2 = FileInfo(None, True, *([None] * 7))
    fi3 = FileInfo(None, False, *([None] * 7))
    fi4 = FileInfo(None, True, *([None] * 7))
    fc1 = FileCollection(None, 'fcol_url', *([None] * 3))
    ri = RedditInfo(None, 'reddit_url', None, "subpath_test", *([None] * 5))
    ri.add_file(fi1)
    ri.add_file(fi2)
    fc1.add_file(fi3)
    fc1.add_file(fi4)
    ri.add_collection(fc1)

    # any_audio_downloads = True
    set_downloaded = {fi4}

    gwa = GWARipper()
    gwa.db_con = DummyCon()
    gwa._download_collection(ri, None)

    assert fc1.downloaded is DownloadErrorCode.COLLECTION_INCOMPLETE
    assert ri.downloaded is DownloadErrorCode.COLLECTION_INCOMPLETE

    assert fi1.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi3.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    # downloaded on _only_ audio is True so selftext will be written
    assert fi4.downloaded is DownloadErrorCode.DOWNLOADED

    assert called_with == {
        # file_idx passed if more than one file
        'download_file': [
            ((fi1, preferred_author_ret, ri, 1, 1), {'dl_max': 4}),
            ((fi2, preferred_author_ret, ri, 2, 2), {'dl_max': 4}),
            ((fi3, preferred_author_ret, ri, 1, 3), {'dl_max': 4}),
            ((fi4, preferred_author_ret, ri, 2, 4), {'dl_max': 4}),
        ],
        'preferred_author': ((), {}),
        'add_to_db_col': ((fc1, preferred_author_ret), {}),
        'add_to_db_ri': ((ri,), {}),
        'write_selftext': (
            (cfg.get_root(), os.path.join(preferred_author_ret, generate_filename_ret[0])), {})
    }
    assert caplog.records[0].message == (
            f"Starting download of collection: {ri.url}")
    

def test_set_urls(setup_tmpdir):

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
        if isinstance(fi, FileCollection):
            fi.downloaded = DownloadErrorCode.COLLECTION_COMPLETE
        else:
            fi.downloaded = DownloadErrorCode.DOWNLOADED

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    with GWARipper() as gwa:
        gwa.extract_and_download(urls[0])
        # extr report appended and downloaded set
        assert gwa.extractor_reports[0] is redditinforep
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.COLLECTION_COMPLETE
        assert len(gwa.extractor_reports) == 1
    # download called
    assert download_called_with is redditinfo
    assert download_called_with.downloaded is DownloadErrorCode.COLLECTION_COMPLETE

    def patched_dl(self, fi):
        assert fi is not None
        nonlocal download_called_with
        download_called_with = fi

    monkeypatch.setattr('gwaripper.gwaripper.GWARipper.download', patched_dl)

    with GWARipper() as gwa:
        gwa.extract_and_download(urls[1])
        # extr report appended and downloaded set
        assert gwa.extractor_reports[0] is soundgasmrep
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.NOT_DOWNLOADED
        assert len(gwa.extractor_reports) == 1
    # download called
    assert download_called_with is soundgasmfi
    assert download_called_with.downloaded is DownloadErrorCode.NOT_DOWNLOADED

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
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.NOT_DOWNLOADED

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
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.NOT_DOWNLOADED

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
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.NOT_DOWNLOADED
        # download not called
        assert download_called_with is None

        # needs to be inside context otherwise db auto bu is run and logs msg
        assert len(caplog.records) == 1
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
        assert gwa.extractor_reports[1].download_error_code is DownloadErrorCode.NOT_DOWNLOADED
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
        if isinstance(fi, FileCollection):
            fi.downloaded = DownloadErrorCode.COLLECTION_COMPLETE
        else:
            fi.downloaded = DownloadErrorCode.DOWNLOADED

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
        assert redditinfo.downloaded is DownloadErrorCode.COLLECTION_COMPLETE

        assert len(gwa.extractor_reports) == 1
        assert gwa.extractor_reports[0] is redditinforep
        assert gwa.extractor_reports[0].download_error_code is redditinfo.downloaded

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
        assert gwa.extractor_reports[0].download_error_code is DownloadErrorCode.NOT_DOWNLOADED


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
        assert gwa._pad_filename_if_exists(tmpdir, 'test', 'txt') == 'test_03'
        assert caplog.records[0].message == 'FILE ALREADY EXISTS - ADDED: _03'

        caplog.clear()
        assert gwa._pad_filename_if_exists(tmpdir, 'foo', 'bar.txt') == 'foo_02'
        assert caplog.records[0].message == 'FILE ALREADY EXISTS - ADDED: _02'

        assert gwa._pad_filename_if_exists(tmpdir, 'baz', '.m4a') == 'baz'


def test_write_report(setup_tmpdir):
    tmpdir = setup_tmpdir

    ecode = ExtractorErrorCode
    reports = [
            ExtractorReport('url1', ecode.NO_ERRORS, DownloadErrorCode.DOWNLOADED),
            ExtractorReport('url2col', ecode.ERROR_IN_CHILDREN, DownloadErrorCode.COLLECTION_INCOMPLETE),
            ExtractorReport('url3', ecode.BANNED_TAG, DownloadErrorCode.NOT_DOWNLOADED),
            ExtractorReport('url4col', ecode.NO_SUPPORTED_AUDIO_LINK, DownloadErrorCode.COLLECTION_INCOMPLETE),
            ExtractorReport('url5col', ecode.NO_ERRORS, DownloadErrorCode.COLLECTION_COMPLETE)
            ]

    reports[1].children = [
            ExtractorReport('url2colurl1', ecode.NO_RESPONSE, DownloadErrorCode.NOT_DOWNLOADED),
            ExtractorReport('url2colurl2', ecode.NO_EXTRACTOR, DownloadErrorCode.NOT_DOWNLOADED),
            ExtractorReport('url2colurl3col', ecode.ERROR_IN_CHILDREN, DownloadErrorCode.COLLECTION_INCOMPLETE),
            ]

    reports[1].children[2].children = [
            ExtractorReport('url2colurl3colurl1', ecode.NO_AUTHENTICATION, DownloadErrorCode.NOT_DOWNLOADED),
            ExtractorReport('url2colurl3colurl2', ecode.NO_ERRORS, DownloadErrorCode.HTTP_ERR_NOT_FOUND),
            ]

    reports[3].children = [
            ExtractorReport('url4colurl1', ecode.NO_ERRORS, DownloadErrorCode.SKIPPED_DUPLICATE),
            ExtractorReport('url4colurl2', ecode.BANNED_TAG, DownloadErrorCode.NOT_DOWNLOADED),
            ]

    reports[4].children = [
            ExtractorReport('url5colurl1', ecode.NO_ERRORS, DownloadErrorCode.SKIPPED_DUPLICATE),
            ExtractorReport('url5colurl2', ecode.NO_ERRORS, DownloadErrorCode.DOWNLOADED),
            ]

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
            "<div class='info'><span class='error '>COLLECTION_INCOMPLETE</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl1\">url2colurl1</a>",
            "<div class='info'><span class='error '>NO_RESPONSE</span></div>",
            "<div class='info'><span class='error '>NOT_DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl2\">url2colurl2</a>",
            "<div class='info'><span class='error '>NO_EXTRACTOR</span></div>",
            "<div class='info'><span class='error '>NOT_DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"collection indent \">",
            "<span>Collection: </span><a href=\"url2colurl3col\">url2colurl3col</a>",
            "<div class='info'><span class='error '>ERROR_IN_CHILDREN</span></div>",
            "<div class='info'><span class='error '>COLLECTION_INCOMPLETE</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl3colurl1\">url2colurl3colurl1</a>",
            "<div class='info'><span class='error '>NO_AUTHENTICATION</span></div>",
            "<div class='info'><span class='error '>NOT_DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url2colurl3colurl2\">url2colurl3colurl2</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='error '>HTTP_ERR_NOT_FOUND</span></div>",
            "</div>",
            "</div>",  # urlcol2url3col
            "</div>",  # url2col
            "<div class=\"block \">",
            "<a href=\"url3\">url3</a>",
            "<div class='info'><span class='error '>BANNED_TAG</span></div>",
            "<div class='info'><span class='error '>NOT_DOWNLOADED</span></div>",
            "</div>",
            "<div class=\"collection \">",
            "<span>Collection: </span><a href=\"url4col\">url4col</a>",
            "<div class='info'><span class='error '>NO_SUPPORTED_AUDIO_LINK</span></div>",
            "<div class='info'><span class='error '>COLLECTION_INCOMPLETE</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url4colurl1\">url4colurl1</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>SKIPPED_DUPLICATE</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url4colurl2\">url4colurl2</a>",
            "<div class='info'><span class='error '>BANNED_TAG</span></div>",
            "<div class='info'><span class='error '>NOT_DOWNLOADED</span></div>",
            "</div>",
            "</div>",  # url4col
            "<div class=\"collection \">",
            "<span>Collection: </span><a href=\"url5col\">url5col</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>COLLECTION_COMPLETE</span></div>",
            "<div class=\"block indent \">",
            "<a href=\"url5colurl1\">url5colurl1</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>SKIPPED_DUPLICATE</span></div>",
            "</div>",
            "<div class=\"block indent \">",
            "<a href=\"url5colurl2\">url5colurl2</a>",
            "<div class='info'><span class='success '>NO_ERRORS</span></div>",
            "<div class='info'><span class='success '>DOWNLOADED</span></div>",
            "</div>",
            "</div>",  # url5col
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
