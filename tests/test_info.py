import os.path

import pytest

from gwaripper.info import (
        FileInfo, FileCollection, RedditInfo, children_iter_dfs,
        DELETED_USR_FOLDER, sanitize_filename
        )
# from gwaripper.extractors.base import BaseExtractor
# doesn't work since it leads to circ dep
from gwaripper.extractors import base, AudioHost
from gwaripper import extractors
from gwaripper.download import DownloadErrorCode


def test_fc_add_file_collection():
    fc1 = FileCollection(base.BaseExtractor, "https://imaginary-audio-playlist/3432209",
                         "3432209", "bestest playlist around that somehow also has a"
                         " needlessly long title that does not seem to end so we "
                         "can test filename generation", "dank-author")
    fc2 = FileCollection(base.BaseExtractor, "https://imaginary-audio-playlist/3432209",
                         "3432209", "bestest playlist around that somehow also has a"
                         " needlessly long title that does not seem to end so we "
                         "can test filename generation", "dank-author")
    fc3 = FileCollection(base.BaseExtractor, "https://imaginary-audio-playlist/3432209",
                         "3432209", "bestest playlist around that somehow also has a"
                         " needlessly long title that does not seem to end so we "
                         "can test filename generation", "dank-author")
    fi1 = FileInfo(base.BaseExtractor, True, 'm4a',
                   "https://soundgasm.net/u/test-1/File-Name-Test",
                   "https://soudngasm.net/4uowl4235248sla242.m4a", None,
                   "This is a test audio", "Description for test audio", "authorname")
    fi2 = FileInfo(base.BaseExtractor, True, 'mp3',
                   "https://eraudica.com/e/Eraudica-Test-Title",
                   "https://eraudica.com/EraudicaTestTitle.mp3?adfs=safs234", None,
                   "This is an eraudica test audio", "eraudica Description", "Eves-garden")

    fc1.add_file(fi1)
    assert fc1._children[0] is fi1
    assert fi1.parent is fc1
    assert fc1.nr_files == 1

    fc1.add_file(fi2)
    assert fc1._children[0] is fi1
    assert fc1._children[1] is fi2
    assert fi2.parent is fc1
    assert fc1.nr_files == 2

    fc2.add_collection(fc3)
    assert fc2._children[0] is fc3
    assert fc3.parent is fc2
    assert fc2.nr_files == 0

    fc3.add_file(fi1)
    assert fc3._children[0] is fi1
    assert fi1.parent is fc3
    assert fc3.nr_files == 1
    assert fc2.nr_files == 1

    fc3.add_collection(fc1)
    assert fc3._children[1] is fc1
    assert fc1.parent is fc3
    assert fc3.nr_files == 3
    assert fc2.nr_files == 3
    assert fc1.nr_files == 2

    fc2.add_file(fi2)
    assert fc2.nr_files == 4
    assert fc3.nr_files == 3
    assert fc1.nr_files == 2


def generate_redditinfo_tree(add_collections=True):
    fi1 = FileInfo(base.BaseExtractor, True, 'm4a',
                   "https://soundgasm.net/u/test-1/File-Name-Test",
                   "https://soudngasm.net/4uowl4235248sla242.m4a", None,
                   "This is a test audio", "Description for test audio", "authorname")
    fi2 = FileInfo(base.BaseExtractor, True, 'mp3',
                   "https://eraudica.com/e/Eraudica-Test-Title",
                   "https://eraudica.com/EraudicaTestTitle.mp3?adfs=safs234", None,
                   "This is an eraudica test audio", "eraudica Description", "Eves-garden")
    fi3 = FileInfo(base.BaseExtractor, True, 'm4a',
                   "https://soundgasm.net/u/test-2/Foo-File-Name-Test",
                   "https://soudngasm.net/ali3425238sdf9232.m4a", None,
                   "This is a super test audio", "Description sfas for test audio", "fooname")
    fi4 = FileInfo(base.BaseExtractor, False, 'mp4',
                   "https://imgur.com/35HLlk54",
                   "https://i.imgur.com/35HLlk54", "35HLlk54",
                   None, "Animated descr", "xhabbaa")
    fi5 = FileInfo(base.BaseExtractor, False, 'jpg', "https://imgur.com/H4sD65ff",
                   "https://i.imgur.com/H4sD65ff", "H4sD65ff",
                   "Title instead of ID", "Still img descr", "xhabbaa")

    fc1 = FileCollection(base.BaseExtractor, "https://imaginary-audio-playlist/3432209",
                         "3432209", "Bestest playlist around that somehow also has a"
                         " needlessly long title that does not seem to end so we "
                         "can test filename generation", "dank-author")
    fc2 = FileCollection(base.BaseExtractor, "https://imgur.com/a/5Fkz89D",
                         "5Fkz89D", "Imgur album TT 0123456789012345 xtra xtra", "xhabbaa")

    ri = RedditInfo(base.BaseExtractor, "https://reddit.com/r/pillowtalkaudio/comments/6ghk3/f4a_"
                    "asmr_breathy_whispers_for_you", "6ghk3", "[F4M][ASMR] Breathy Whispers "
                    "For You [Extremely Long Title] ⛸📱🤳🤵 This Title Is Supposed To Be "
                    "Ridiculously Long [With] [So Many More Tags] [Max Path Is Crying Right Now] "
                    "🤢✔😎🙌 [#EmojisMakeEverythingBetter]", "xhabbaa", "pillowtalkaudio",
                    "/r/pillowtalkaudio/comments/6ghk3/f4a_", 12345.0,
                    "flair", 1337)

    # only set parent on fileinfos since we might test parent propagation
    fc1.add_file(fi3)

    fc2.add_file(fi4)
    fc2.add_file(fi5)

    ri.add_file(fi1)
    ri.add_file(fi2)

    if add_collections:
        ri.add_collection(fc1)
        ri.add_collection(fc2)

    return fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri


def test_parent_sets_reddit_info():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=False)

    # setting parent on a FileCollection should propagate the parent
    # which currently is only allowed to be RedditInfo to it's
    # children
    assert fc1.parent is None
    assert fi3.reddit_info is None
    fc1.parent = ri
    assert fi3.reddit_info is ri

    assert fc2.parent is None
    assert fi4.reddit_info is None
    assert fi5.reddit_info is None
    fc2.parent = ri
    assert fi4.reddit_info is ri
    assert fi5.reddit_info is ri


def test_finfo_find_rinfo_on_parent_set():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=False)

    # looks similar to test_parent_sets_reddit_info but here we test that
    # when a parent that has a RedditInfo as parent somewhere in the chain
    # gets set on a FileInfo that FileInfo finds and sets that RedditInfo
    # to it's own attrib fi.reddit_info

    # set parent to diff fcol
    fi1.parent = FileCollection(*([None]*5))
    assert fi1.reddit_info is None
    fi1.parent = ri
    assert fi1.reddit_info is ri

    assert fi3.reddit_info is None
    fi3.parent = fi1
    assert fi3.reddit_info is ri

    fc2.parent = ri
    fi4.reddit_info = None
    assert fi4.reddit_info is None
    fi4.parent = fc2
    assert fi4.reddit_info is ri


def test_fcol_nr_files():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)
    assert ri.nr_files == 5

    fc1.nr_files += -1
    assert fc1.nr_files == 0
    assert ri.nr_files == 4

    fc1.nr_files += 4
    assert fc1.nr_files == 4
    assert ri.nr_files == 8

    fc2.nr_files = 0
    assert fc2.nr_files == 0
    assert fc1.nr_files == 4
    assert ri.nr_files == 6

    # doesnt change others
    fc2.parent = None
    fc2.nr_files = 7
    assert fc2.nr_files == 7
    assert fc1.nr_files == 4
    assert ri.nr_files == 6


def test_fcol_subpath():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)
    # NOTE: original title ends on a space at char 70 which is important to test that
    # subpath strips spaces from subpath
    assert ri.subpath == ("[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] "
                          "____ This")

    # subpath gets generated in __init__ so we have to gen a new one
    ri = RedditInfo(base.BaseExtractor, "url", "6ghk3", None, "xhabbaa",
                    "pillowtalkaudio", "/r/pillowtalkaudio/comments/6ghk3/f4a_", 12345.0,
                    "flair", 1337)
    ri.nr_files = 4
    assert ri.subpath == ri.id

    assert fc2.subpath == ""
    fc2.nr_files = 3
    assert fc2.subpath == fc2.title


def test_preferred_author():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)

    assert ri.get_preferred_author_name() == ri.author
    ri.author = None
    assert ri.get_preferred_author_name() == fi1.author

    assert fc2.get_preferred_author_name() == fc2.author
    fc2.author = None
    assert fc2.get_preferred_author_name() == fi4.author

    for _, c in children_iter_dfs(ri.children, file_info_only=False):
        c.author = None

    # reddit info but no author foudn -> deleted user
    assert ri.get_preferred_author_name() == DELETED_USR_FOLDER

    assert fc2.get_preferred_author_name() == "_unknown_user_files"


def test_downloaded_set_on_report():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)
    exerr = base.ExtractorErrorCode
    rep = base.ExtractorReport('url', exerr.NO_ERRORS)
    fi1.report = rep
    # should be error codes but doesn't really matter
    fi1.downloaded = True
    assert fi1.report.download_error_code is True
    fi1.downloaded = False
    assert fi1.report.download_error_code is False

    rep = base.ExtractorReport('url', exerr.NO_ERRORS)
    ri.report = rep
    ri.downloaded = True
    assert ri.report.download_error_code is True
    ri.downloaded = False
    assert ri.report.download_error_code is False


def test_generate_filename():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)

    #
    # no title or id
    #
    fi_none = FileInfo(*([None]*9))
    fi_none.generate_filename(None, 0) == ('', 'unnamed', None)

    #
    # NO PARENT
    #
    fi_none.title = ("[F4M] Déjà vu, but I'm blind [äö-.-üö] [🤳🎂👀] [ASMR] [Tag1] [Tag2]"
                     " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
                     " sit amet] [soungasm.net] [💋🤔👌 #EmojisSoDank ❤👱🤴🥞] sdkfjslkjflks"
                     "skgslk dsfkjsalkfs sdfkjsaldfd dsflksajdlkf dfklasjlkfd skdf")
    fi_none.ext = "m4a"
    assert fi_none.generate_filename(None) == (
            "",
            "[F4M] Déjà vu, but I_m blind [äö-.-üö] [___] [ASMR] [Tag1] [Tag2]"
            " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
            " sit amet] [soungasm.net] [___ _EmojisSoDank ____]",
            "m4a")

    assert fi_none.generate_filename(None, 5) == (
            "",
            "05_[F4M] Déjà vu, but I_m blind [äö-.-üö] [___] [ASMR] [Tag1] [Tag2]"
            " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
            " sit amet] [soungasm.net] [___ _EmojisSoDank __",
            "m4a")

    #
    # REDDIT SUBPATH
    #

    assert fi4.generate_filename(ri, 0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")
    assert fi4.generate_filename(ri, 9) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Imgur album TT 012345678901234_09_35HLlk54",
            "mp4")
    bu = ri.title
    ri.title = None
    ri._update_subpath()
    assert fi4.generate_filename(ri, 0) == (
            "6ghk3",
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")

    #
    # REDDIT BUT NO SUBPATH
    #
    ri.title = bu
    ri._update_subpath()

    bu = ri.children
    ri._children = [fc2]
    ri.nr_files = 2  # < 3 FileInfo children -> no subpath
    assert fi4.generate_filename(ri, 0) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This_"
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")
    assert fi4.generate_filename(ri, 3) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This_"
            "Imgur album TT 012345678901234_03_35HLlk54",
            "mp4")

    ri._children = bu
    ri.nr_files = 5

    #
    # REDDIT SUBPATH direct parent is reddit -> parent_title does not get appended
    #
    assert fi1.generate_filename(ri, 0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "This is a test audio",
            "m4a")
    assert fi1.generate_filename(ri, 9) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "09_This is a test audio",
            "m4a")
    bu = ri.title
    ri.title = None
    ri._update_subpath()
    assert fi1.generate_filename(ri, 0) == (
            "6ghk3",
            "This is a test audio",
            "m4a")

    #
    # REDDIT BUT NO SUBPATH but direct parent is reddit
    # -> parent_title does not get appended
    #
    ri.title = bu
    ri._update_subpath()

    bu = ri.children
    ri.nr_files = 0  # < 3 FileInfo children -> no subpath
    ri._children = []
    assert fi2.generate_filename(ri, 0) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This_"
            "This is an eraudica test audio",
            "mp3")
    assert fi2.generate_filename(ri, 4) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This_"
            "04_This is an eraudica test audio",
            "mp3")

    ri._children = bu
    ri.nr_files = 5
    #
    # LONG PARENT TITLE
    #
    assert fi3.generate_filename(ri, 0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Bestest playlist around that s_This is a super test audio",
            "m4a")

    #
    # LONG PARENT TITLE WITH NO REDDITINFO
    #
    fc1.parent = None
    # begin and end in spaces to test that no file path begins/ends in spaces
    # space at cut-off point (70th char) but it doesn't need to get removed here since
    # filename follows anyway
    fc1.title = " Bestest playlist around that somehow al 1234567890 1234567890 1234  7  "
    assert fi3.generate_filename(fc1, 0) == (
            "",
            "Bestest playlist around that somehow al 1234567890 1234567890 1234  7_This is a super test audio",
            "m4a")


def test_generate_filename_nested(monkeypatch):
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=False)

    #
    # NESTED FILECOL (not allowed currently but it's in the function)
    #
    # NOTE: needs patched FileCollection.parent.setter to work

    def patched_parent_setter(self, parent):
        self._parent = parent

        reddit_info = parent
        if not isinstance(parent, RedditInfo):
            reddit_info = None
            p = parent
            while p:
                p = p.parent
            # RedditInfo always root
            if isinstance(p, RedditInfo):
                reddit_info = p

        for child in self.children:
            child.reddit_info = reddit_info

    # patch parent.setter which is read-only by replacing the whole property
    # parent.setter(new setter func) returns property with new setter function
    patched_prop = FileCollection.parent.setter(patched_parent_setter)
    monkeypatch.setattr('gwaripper.info.FileCollection.parent', patched_prop)

    fc1.add_collection(fc2)

    # for testing that no subpaths begin/end in spaces
    fc1.title = (" Bestest playlist around that somehow also has a n e   67890"
                 # beginning space gets removed so space 70th will be 69th
                 #         v 70th char (incl ' ')
                 "1234567890 23")
    fc1._update_subpath()
    #                                                    v 41th char
    fc2.title = " Imgur album TT 01234567  012345 xtra xt a "
    fc2._update_subpath()

    assert fi4.parent is fc2
    assert fc2.parent is fc1

    # topmost parent will be only subpath and direct parent gets appended to name
    assert fi4.generate_filename(fc1, 2) == (
            "Bestest playlist around that somehow also has a n e   678901234567890",
            "Imgur album TT 01234567  0123_02_35HLlk54",
            "mp4")
    assert fi4.generate_filename(fc1, 0) == (
            "Bestest playlist around that somehow also has a n e   678901234567890",
            "Imgur album TT 01234567  0123_35HLlk54",
            "mp4")

    # no subpath
    fc1.nr_files = 2
    assert fi4.generate_filename(fc1, 0) == (
            "",
            "Bestest playlist around that somehow also has a n e   678901234567890_"
            "Imgur album TT 01234567  0123_35HLlk54",
            "mp4")
    assert fi4.generate_filename(fc1, 1) == (
            "",
            "Bestest playlist around that somehow also has a n e   678901234567890_"
            "Imgur album TT 01234567  0123_01_35HLlk54",
            "mp4")

    # subpath but direct parent is topmost parent -> don't append to name
    fc2.parent = None
    fc2.nr_files = 3
    fc2.title = " Imgur album TT 01234567  012345 xtra xt a 456789012345678901234567890 2"
    fc2._update_subpath()
    assert fi4.generate_filename(fc2, 0) == (
            "Imgur album TT 01234567  012345 xtra xt a 456789012345678901234567890",
            "35HLlk54",
            "mp4")
    assert fi4.generate_filename(fc2, 5) == (
            "Imgur album TT 01234567  012345 xtra xt a 456789012345678901234567890",
            "05_35HLlk54",
            "mp4")


def test_get_topmost_parent():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(add_collections=True)

    assert fi3.get_topmost_parent() is ri  # fi3.parent == fc1
    assert fi4.get_topmost_parent() is ri

    fc1.parent = None
    assert fi3.get_topmost_parent() is fc1

    fc1.parent = fc2
    assert fi3.get_topmost_parent() is ri

    fc2.parent = None
    assert fi3.get_topmost_parent() is fc2


@pytest.mark.parametrize(
        'subpath, filename, expected',
        [("", '         Starts and ends with spaces        ', 'Starts and ends with spaces'),
         ("", r'Allowed chars -_.,[] end', r'Allowed chars -_.,[] end'),
         ("", r'Disallowed chars ~:}{?/\`!@#$%^&*', r'Disallowed chars ________________'),
         ("01234567890123456789012345678901234567890123456789012345678901234567890123456789"
          "0123456789012345678901234567890123456789012345678901234567890123456789",  # 150c
          "Truncate to 35 chars012345678901234", "Truncate to 35 chars012345678901234"),
         ("01234567890123456789012345678901234567890123456789012345678901234567890123456789"
          "0123456789012345678901234567890123456789012345678901234567890123456789",  # 150c
          "Truncate to 35 chars0123456789012345678", "Truncate to 35 chars012345678901234"),
         # test that we strip before truncation
         ("01234567890123456789012345678901234567890123456789012345678901234567890123456789"
          "0123456789012345678901234567890123456789012345678901234567890123456789",  # 150c
          "      Truncate to 35 chars012345678901234    ", "Truncate to 35 chars012345678901234"),
         # test that we also strip after truncation
         ("01234567890123456789012345678901234567890123456789012345678901234567890123456789"
          "0123456789012345678901234567890123456789012345678901234567890123456789",  # 150c
          " Truncate to 35 chars01234567890123 5 ", "Truncate to 35 chars01234567890123"),
         ])
def test_sanitize_filename(subpath, filename, expected):
    assert sanitize_filename(subpath, filename) == expected


def test_sanitize_filename_asserts():
    with pytest.raises(AssertionError):
        sanitize_filename(" assert fires", "test")
    with pytest.raises(AssertionError):
        sanitize_filename("assert fires ", "test")
    with pytest.raises(AssertionError):
        sanitize_filename(
            "assert fires assert fires assert fires assert fires assert fires "
            "assert fires assert fires assert fires assert fires assert fires "
            "assert fires assert fires assert fires assert fires ", "test")


def test_choose_mirrors_only_one_host():
    fc = FileCollection(None, "url", *[None]*3)
    fi1 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi2 = FileInfo(extractors.ImgurImageExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fc1 = FileCollection(extractors.SoundgasmUserExtractor, "url", *[None]*3)
    fc2 = FileCollection(extractors.ImgurAlbumExtractor, "url", *[None]*3)

    fc.add_file(fi1)
    fc.add_file(fi2)
    fc.add_collection(fc1)
    fc.add_collection(fc2)

    fc.choose_mirrors([AudioHost.EROCAST])

    # should still have default, since there's only one host
    assert fi1.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fc1.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN
    assert fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN


def test_choose_mirrors_imbalanced_files():
    fc = FileCollection(None, "url", *[None]*3)
    fi1 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi2 = FileInfo(extractors.ImgurImageExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi3 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fc1 = FileCollection(extractors.SoundgasmUserExtractor, "url", *[None]*3)
    fc2 = FileCollection(extractors.ImgurAlbumExtractor, "url", *[None]*3)

    fc.add_file(fi1)
    fc.add_file(fi2)
    fc.add_file(fi3)
    fc.add_collection(fc1)
    fc.add_collection(fc2)

    fc.choose_mirrors([AudioHost.EROCAST])

    # should still have default, since not all files were present on all mirrors
    assert fi1.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi3.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fc1.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN
    assert fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN

def test_choose_mirrors_pick_highest():
    fc = FileCollection(None, "url", *[None]*3)
    fi1 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi2 = FileInfo(extractors.ImgurImageExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi3 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi4 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fc1 = FileCollection(extractors.SoundgasmUserExtractor, "url", *[None]*3)
    fc2 = FileCollection(extractors.ImgurAlbumExtractor, "url", *[None]*3)

    fc.add_file(fi1)
    fc.add_file(fi2)
    fc.add_file(fi3)
    fc.add_file(fi4)
    fc.add_collection(fc1)
    fc.add_collection(fc2)

    fc.choose_mirrors([AudioHost.EROCAST, AudioHost.SOUNDGASM, AudioHost.WHYP])

    # should skip Soundgasm links
    assert fi1.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi3.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi4.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fc1.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
    assert fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN


def test_choose_mirrors_not_in_prio_list():
    fc = FileCollection(None, "url", *[None]*3)
    fi1 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi2 = FileInfo(extractors.ImgurImageExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi3 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi4 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fc1 = FileCollection(extractors.SoundgasmUserExtractor, "url", *[None]*3)
    fc2 = FileCollection(extractors.ImgurAlbumExtractor, "url", *[None]*3)

    fc.add_file(fi1)
    fc.add_file(fi2)
    fc.add_file(fi3)
    fc.add_file(fi4)
    fc.add_collection(fc1)
    fc.add_collection(fc2)

    fc.choose_mirrors([])

    # should skip ONE of the hosts
    assert (
        (fi1.downloaded is DownloadErrorCode.NOT_DOWNLOADED
            and fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
            and fi3.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
            and fi4.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
            and fc1.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN
            and fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN)
        or
        (fi1.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
            and fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
            and fi3.downloaded is DownloadErrorCode.NOT_DOWNLOADED
            and fi4.downloaded is DownloadErrorCode.NOT_DOWNLOADED
            and fc1.downloaded is DownloadErrorCode.CHOSE_OTHER_HOST
            and fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN)
    )

def test_choose_mirrors_keep_all_hosts_not_equal_dist():
    # mirrors evenly divided by nr of different hosts, but not all files
    # are present on all hosts
    fc = FileCollection(None, "url", *[None]*3)
    fi1 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi2 = FileInfo(extractors.ImgurImageExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi3 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi4 = FileInfo(extractors.ErocastExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi5 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fi6 = FileInfo(extractors.SoundgasmExtractor, True, "m4a", "pgurl", "url", *[None]*4)
    fc1 = FileCollection(extractors.SoundgasmUserExtractor, "url", *[None]*3)
    fc2 = FileCollection(extractors.ImgurAlbumExtractor, "url", *[None]*3)

    fc.add_file(fi1)
    fc.add_file(fi2)
    fc.add_file(fi3)
    fc.add_file(fi4)
    fc.add_file(fi5)
    fc.add_file(fi6)
    fc.add_collection(fc1)
    fc.add_collection(fc2)

    fc.choose_mirrors([AudioHost.EROCAST, AudioHost.SOUNDGASM, AudioHost.WHYP])

    # should skip none
    assert fi1.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi2.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi3.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi4.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi5.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fi6.downloaded is DownloadErrorCode.NOT_DOWNLOADED
    assert fc1.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN
    assert fc2.downloaded is DownloadErrorCode.ERROR_IN_CHILDREN
