import os.path

import pytest

from gwaripper.info import (
        FileInfo, FileCollection, RedditInfo, children_iter_dfs,
        DELETED_USR_FOLDER, sanitize_filename
        )
# from gwaripper.extractors.base import BaseExtractor
# doesn't work since it leads to circ dep
from gwaripper.extractors import base


def test_reddit_info_no_parents_allowed():
    ri = RedditInfo(None, None, None, None, None, None, 'sfasd', 1234.0)
    with pytest.raises(AssertionError) as exc:
        ri.parent = RedditInfo(None, None, None, None, None, None, 'sfasd', 1234.0)
    assert "RedditInfo is not allowed to have a parent!" == str(exc.value)


def generate_redditinfo_tree(parent_set_fcol=False):
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
                    "/r/pillowtalkaudio/comments/6ghk3/f4a_", 12345.0)

    # only set parent on fileinfos since we might test parent propagation
    fi3.parent = fc1
    fc1.children.append(fi3)

    fi4.parent = fc2
    fc2.children.append(fi4)
    fi5.parent = fc2
    fc2.children.append(fi5)

    if parent_set_fcol:
        fc1.parent = ri
        fc2.parent = ri

    fi1.parent = ri
    ri.children.append(fi1)
    fi2.parent = ri
    ri.children.append(fi2)
    ri.children.append(fc1)
    ri.children.append(fc2)

    return fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri


def test_parent_sets_reddit_info():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree()

    # check that reddit_info not

    assert fi3.reddit_info is None
    fc1.parent = ri
    assert fi3.reddit_info is ri

    assert fi4.reddit_info is None
    assert fi5.reddit_info is None
    fc2.parent = ri
    assert fi4.reddit_info is ri
    assert fi5.reddit_info is ri


def test_fcol_nr_files():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(parent_set_fcol=True)
    assert ri.nr_files() == 5
    fc2.children = [fi4]
    assert ri.nr_files() == 4
    ri.children = [fc2, fi1]
    assert ri.nr_files() == 2


def test_fcol_subpath():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(parent_set_fcol=True)
    assert ri.subpath == ("[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] "
                          "____ This Title Is Supposed To Be Ridiculously Long [With] "
                          "[So Many More Tags] [Max Path Is Crying Right Now] ____ [_EmojisMa")
    ri.title = None
    assert ri.subpath == ri.id

    assert fc2.subpath == ""
    fc2.children = [fi1, fi2, fi4]
    assert fc2.subpath == fc2.title


def test_preferred_author():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(parent_set_fcol=True)

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


def test_finfo_find_rinfo_on_parent_set():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree()

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


def test_downloaded_set_on_report():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree()
    exerr = base.ExtractorErrorCode
    rep = base.ExtractorReport('url', exerr.NO_ERRORS)
    fi1.report = rep
    fi1.downloaded = True
    assert fi1.report.downloaded is True
    fi1.downloaded = False
    assert fi1.report.downloaded is False

    rep = base.ExtractorReport('url', exerr.NO_ERRORS)
    ri.report = rep
    ri.downloaded = True
    assert ri.report.downloaded is True
    ri.downloaded = False
    assert ri.report.downloaded is False


def test_update_downloaded():
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree()

    # fc2 [fi4, fi5]
    fi4.downloaded = True
    fi5.downloaded = False
    assert fc2.update_downloaded() is False
    assert fc2.downloaded is False
    assert fi4.downloaded is True
    assert fi5.downloaded is False

    fi5.downloaded = True
    assert fc2.update_downloaded() is True
    assert fc2.downloaded is True
    assert fi4.downloaded is True
    assert fi5.downloaded is True

    # ri [fi1, fi2, fc1 [fi3], fc2 [fi4, fi5]]
    # only one false children -> ri.downloaded also false
    # but fc1 not sinc only child fi3 is True
    fi1.downloaded = True
    fi2.downloaded = True
    fi3.downloaded = True
    fi4.downloaded = True
    fi5.downloaded = False

    assert ri.update_downloaded() is False
    assert ri.downloaded is False
    assert fc2.downloaded is False
    assert fc1.downloaded is True
    # children file infos unchanged
    assert fi1.downloaded is True
    assert fi2.downloaded is True
    assert fi3.downloaded is True
    assert fi4.downloaded is True
    assert fi5.downloaded is False

    fi5.downloaded = True
    assert ri.update_downloaded() is True
    assert ri.downloaded is True
    assert fc2.downloaded is True
    assert fc1.downloaded is True


def test_generate_filename(monkeypatch):
    fi1, fi2, fi3, fi4, fi5, fc1, fc2, ri = generate_redditinfo_tree(parent_set_fcol=True)

    #
    # no title or id
    #
    fi_none = FileInfo(*([None]*9))
    fi_none.generate_filename(0) == ('', 'unnamed', None)

    #
    # NO PARENT
    #
    fi_none.title = ("[F4M] Déjà vu, but I'm blind [äö-.-üö] [🤳🎂👀] [ASMR] [Tag1] [Tag2]"
                     " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
                     " sit amet] [soungasm.net] [💋🤔👌 #EmojisSoDank ❤👱🤴🥞] sdkfjslkjflks"
                     "skgslk dsfkjsalkfs sdfkjsaldfd dsflksajdlkf dfklasjlkfd skdf")
    fi_none.ext = "m4a"
    assert fi_none.generate_filename() == (
            "",
            "[F4M] Déjà vu, but I_m blind [äö-.-üö] [___] [ASMR] [Tag1] [Tag2]"
            " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
            " sit amet] [soungasm.net] [___ _EmojisSoDank ____]",
            "m4a")

    assert fi_none.generate_filename(5) == (
            "",
            "05_[F4M] Déjà vu, but I_m blind [äö-.-üö] [___] [ASMR] [Tag1] [Tag2]"
            " [Re-post] [Extra Long Title] [Not Long Enough Yet] [Lorem ipsum dolor"
            " sit amet] [soungasm.net] [___ _EmojisSoDank __",
            "m4a")

    #
    # REDDIT SUBPATH
    #

    assert fi4.generate_filename(0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")
    assert fi4.generate_filename(9) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Imgur album TT 012345678901234_09_35HLlk54",
            "mp4")
    bu = ri.title
    ri.title = None
    assert fi4.generate_filename(0) == (
            "6ghk3",
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")

    #
    # REDDIT BUT NO SUBPATH
    #
    ri.title = bu
    bu = ri.children
    ri.children = [fc2]  # < 3 FileInfo children -> no subpath
    assert fi4.generate_filename(0) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This _"
            "Imgur album TT 012345678901234_35HLlk54",
            "mp4")
    assert fi4.generate_filename(3) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This _"
            "Imgur album TT 012345678901234_03_35HLlk54",
            "mp4")

    ri.children = bu

    #
    # REDDIT SUBPATH direct parent is reddit -> parent_title does not get appended
    #
    assert fi1.generate_filename(0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "This is a test audio",
            "m4a")
    assert fi1.generate_filename(9) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "09_This is a test audio",
            "m4a")
    bu = ri.title
    ri.title = None
    assert fi1.generate_filename(0) == (
            "6ghk3",
            "This is a test audio",
            "m4a")

    #
    # REDDIT BUT NO SUBPATH but direct parent is reddit
    # -> parent_title does not get appended
    #
    ri.title = bu
    bu = ri.children
    ri.children = []  # < 3 FileInfo children -> no subpath
    assert fi2.generate_filename(0) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This _"
            "This is an eraudica test audio",
            "mp3")
    assert fi2.generate_filename(4) == (
            "",
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This _"
            "04_This is an eraudica test audio",
            "mp3")

    ri.children = bu
    #
    # LONG PARENT TITLE
    #
    assert fi3.generate_filename(0) == (
            "[F4M][ASMR] Breathy Whispers For You [Extremely Long Title] ____ This",
            "Bestest playlist around that s_This is a super test audio",
            "m4a")

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

    fc1.parent = None
    fc1.children.append(fc2)
    fc2.parent = fc1

    # for testing that no subpaths begin/end in spaces
    # beginning space gets removed so space b4 e will be 50th
    #                                                             v 50th char (incl ' ')
    fc1.title = " Bestest playlist around that somehow also has a n e       "
    #                                     v 26th char normally ends ther
    fc2.title = " Imgur album TT 01234567  012345 xtra xtra "

    # direct parent doesn't have subpath
    assert fi4.generate_filename(2) == (
                os.path.join(
                    "Bestest playlist around that somehow also has a n", ""),
            "Imgur album TT 01234567  012345 xtra xt_02_35HLlk54",
            "mp4")
    assert fi4.generate_filename(0) == (
                os.path.join(
                    "Bestest playlist around that somehow also has a n", ""),
            "Imgur album TT 01234567  012345 xtra xt_35HLlk54",
            "mp4")

    # +1 child -> now has subpath
    fc2.children.append(fi_none)
    assert fi4.generate_filename(0) == (
                os.path.join(
                    "Bestest playlist around that somehow also has a n",
                    "Imgur album TT 01234567"),
            "35HLlk54",
            "mp4")
    assert fi4.generate_filename(1) == (
                os.path.join(
                    "Bestest playlist around that somehow also has a n",
                    "Imgur album TT 01234567"),
            "01_35HLlk54",
            "mp4")


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