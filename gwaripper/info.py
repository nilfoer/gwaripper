import os
import logging
import re

from enum import Enum, auto, unique

from typing import (
        Optional, Union, List, Type, Tuple, Iterator, Sequence,
        Deque, TYPE_CHECKING, cast, overload
        )
from typing_extensions import Literal

from collections import deque

from .download import DownloadErrorCode

# https://www.stefaanlippens.net/circular-imports-type-hints-python.html
# only reason for possible circular dependency here is because
# of type hinting -> use a *conditional import* that is only active in
# "type hinting mode"
# from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .extractors.base import BaseExtractor, ExtractorReport


logger = logging.getLogger(__name__)

DELETED_USR_FOLDER = "deleted_users"
UNKNOWN_USR_FOLDER = "_unknown_user_files"
# own limit; nothing to do with OS dependent MAX_PATH
FILENAME_MAX_LEN = 185


# python passes a _new_ reference to a function that points to the string obj
# so the string is not copied but you also can't modify the reference at the
# caller's location
def sanitize_filename(subpath: str, filename: str):
    # folder names must not start or end with spaces
    assert subpath.strip() == subpath
    # [^\w\-_\.,\[\] ] -> match not(^) any of \w \- _  and whitepsace etc.,
    # replace any that isnt in the  [] with _
    chars_remaining = FILENAME_MAX_LEN - len(subpath)
    assert chars_remaining >= 30
    return re.sub(r"[^\w\-_.,\[\] ]", "_", filename.strip()[:chars_remaining].strip())


# start_list: List[..] resulted in type error
# Argument 1 to "children_iter_dfs" has incompatible type "List[FileInfo]";
# expected "List[Union[FileInfo, FileCollection]]"
#
# Compatibility of container types
# The following program generates a mypy error, since List[int] is not
# compatible with List[object]:
#
# def f(l: List[object], k: List[int]) -> None:
#     l = k  # Type check error: incompatible types in assignment
#
# The reason why the above assignment is disallowed is that allowing the
# assignment could result in non-int values stored in a list of int:
# def f(l: List[object], k: List[int]) -> None:
#     l = k
#     l.append('x')
#     print(k[-1])  # Ouch; a string in List[int]
#
# Sequence is covariant and immutable unlike List[x] which is invariant and allows mutation
# most mutable generic collections are invariant
# class A: ...
# class B(A): ...
#
# lst = [A(), A()]  # Inferred type is List[A]
# new_lst = [B(), B()]  # inferred type is List[B]
# lst = new_lst  # mypy will complain about this, because List is invariant
#
# def f_bad(x: List[A]) -> A:
    # return x[0]
# f_bad(new_lst) # Fails

# def f_good(x: Sequence[A]) -> A:
    # return x[0]
# f_good(new_lst) # OK

# overload return type of iter function based on file_info_only param
# overload decoreated declarations are not allowed to have a function body
# and have to be adjacent to the actual implementation
# using Literal introduced in py3.8 (or from typing_extension pkg) it would
# be possible to have an overload based on the caller passing a literal True
# or False (a variable would still just have type bool unless annoteted with
# Literal[True/False])
@overload
def children_iter_dfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: Literal[False],
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, Union['FileInfo', 'FileCollection']]]: ...


@overload
def children_iter_dfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: Literal[True],
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, 'FileInfo']]: ...


# only allow literals for file_info_only otherwise we'd do one more overload
# for a normal bool
def children_iter_dfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: bool,  # can't be a default arg
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, Union['FileInfo', 'FileCollection']]]:
    """
    Iterator over a list containing FileInfo or FileCollection objects and their
    childrne using DFS
    (Iterates over all the files until it finds a collection then it iterates over
     those files first and so on)
    Yields 2-tuple of 0-based index and Union[FileInfo, FileCollection]
    :param relative_enum: Yield relative index when iterating: e.g. Fi0 Fc1 (Fi0 Fi1 Fi2) Fi2
                          otherwise global Fi0 Fc1 (Fi2 Fi3 Fi4) Fi5
    :param file_info_only: Only iterator over FileInfo instances
    """
    # NOTE: dfs to iter all of the downloads since FileCollections can be recursive
    # only one level though since only RedditInfo is allowed as parent for FileCollection
    stack: List[Tuple[int, int, Sequence[Union['FileInfo', 'FileCollection']]]] = []
    cur_collection: Sequence[Union['FileInfo', 'FileCollection']] = start_list
    i = 0
    enumerator = 0
    skipped_fcols = 0
    while True:
        if i >= len(cur_collection):
            if not stack:
                break
            else:
                i, skipped_fcols, cur_collection = stack.pop()
                continue
        cur = cur_collection[i]
        try:
            # ignoring type error by casting since we just assume it's a file collection
            # and except the error when it's not
            children = cast(FileCollection, cur).children
            stack.append((i + 1, skipped_fcols + 1, cur_collection))
            if not file_info_only:
                yield i if relative_enum else enumerator, cur
                enumerator += 1
            cur_collection = children
            i = 0
            skipped_fcols = 0
        except AttributeError:
            # not a FileCollection
            if relative_enum:
                yield i - skipped_fcols if file_info_only else i, cur
            else:
                yield enumerator, cur
            i += 1
            enumerator += 1


@overload
def children_iter_bfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: Literal[False],
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, Union['FileInfo', 'FileCollection']]]: ...


@overload
def children_iter_bfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: Literal[True],
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, 'FileInfo']]: ...


def children_iter_bfs(start_list: Sequence[Union['FileInfo', 'FileCollection']],
                      file_info_only: bool,
                      relative_enum: bool = False) -> Iterator[
                              Tuple[int, Union['FileInfo', 'FileCollection']]]:
    """
    Iterator over a list containing FileInfo or FileCollection objects and their
    childrne using DFS
    (Iterates over all the files until it finds a collection then it iterates over
     those files first and so on)
    Yields 2-tuple of 0-based index and Union[FileInfo, FileCollection]
    :param relative_enum: Yield relative index when iterating: e.g. Fi0 Fc1 (Fi0 Fi1 Fi2) Fi2
                          otherwise global Fi0 Fc1 (Fi2 Fi3 Fi4) Fi5
    :param file_info_only: Only iterator over FileInfo instances
    """
    # NOTE: bfs to iter all of the downloads since FileCollections can be recursive
    # only one level though since only RedditInfo is allowed as parent for FileCollection

    # queue all the list items here and then queue all children if we
    # come across a FileCollection

    # Easier to ask for forgiveness than permission
    # try/except most pythonic, hasattr also okay since goes well with duck typing
    # using isinstance and type not so good
    #
    # asking for permission vs for forgiveness - performance
    # (hasattr vs try/except AttributeError)
    # Both approaches are, in my opinion, equally valid, at least in terms of
    # readability and pythonic-ness. But if 90% of your objects do not have the
    # attribute bar you'll notice a distinct performance difference between the
    # two approaches: forgiveness 2.95s vs permission 1.04s
    # 90% objects have attr: forgiveness 0.31s vs permission 0.48s
    if file_info_only and relative_enum:
        q: Deque[Tuple[int, Union['FileInfo', 'FileCollection']]] = deque()
        i = -1
        for child in start_list:
            if not hasattr(child, 'children'):
                i += 1
            q.append((i, child))
    else:
        q = deque([(i, item) for i, item in enumerate(start_list)])

    enumerator = 0
    while q:
        i, cur = q.popleft()
        try:
            # ignoring type error since we just assume it's a file collection
            # and except the error when it's not
            children = cast(FileCollection, cur).children
            if file_info_only and relative_enum:
                i = -1
                for child in children:
                    if not hasattr(child, 'children'):
                        i += 1
                    q.append((i, child))
                continue

            q.extend([(i, item) for i, item in
                      enumerate(children)])

            if not file_info_only:
                yield i if relative_enum else enumerator, cur
                enumerator += 1
        except AttributeError:
            # not a FileCollection
            yield i if relative_enum else enumerator, cur
            enumerator += 1



@unique
class DownloadType(Enum):
    HTTP = 0
    HLS = auto()


# from .extractors.base import BaseExtractor
# does not work due to circular dependency
# to use a forward reference (PEP484):
# When a type hint contains names that have not been defined yet, that
# definition may be expressed as a string literal, to be resolved later
# <py3.7 you have to use a string explicitly
# p3.7+ you can do: from __future__ import annotations
# -> and all the type hints will become strings implicitly
# Type[C] refers to subclasses of C instead of instances
class FileInfo:
    def __init__(self, extractor: Type['BaseExtractor'], is_audio: bool, ext: str,
                 page_url: str, direct_url: str, _id: Optional[str],
                 title: Optional[str], descr: Optional[str], author: Optional[str],
                 download_type: DownloadType = DownloadType.HTTP,
                 parent: Optional['FileCollection'] = None,
                 reddit_info: Optional['RedditInfo'] = None):
        self.extractor = extractor
        self.is_audio = is_audio
        self.ext = ext
        self.page_url = page_url
        self.direct_url = direct_url
        self.id = _id
        self.title = title
        self.descr = descr
        self.author = author
        self._parent: Optional['FileCollection'] = None
        self.parent = parent
        # NOTE: automatically set/reset when parent gets set
        self.reddit_info = reddit_info
        self._downloaded: DownloadErrorCode = DownloadErrorCode.NOT_DOWNLOADED
        self.id_in_db: Optional[int] = None
        self.download_type = download_type
        self.report: Optional[ExtractorReport] = None

    def __str__(self):
        return f"FileInfo<{self.page_url}>"

    @property
    def downloaded(self):
        return self._downloaded

    @downloaded.setter
    def downloaded(self, value: DownloadErrorCode):
        self._downloaded = value
        if self.report is not None:
            self.report.download_error_code = value

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent: 'FileCollection'):
        # NOTE: automatically sets/finds reddit_info if there is one!
        self._parent = parent

        self.reddit_info = None
        while parent:
            # RedditInfo won't have a parent
            if isinstance(parent, RedditInfo):
                self.reddit_info = parent
            parent = parent.parent

    def get_topmost_parent(self) -> Optional['FileCollection']:
        p = self.parent
        while True:
            if not p.parent:
                break
            p = p.parent
        return p

    def generate_filename(self, top_parent: Optional['FileCollection'],
                          file_index: int = 0) -> Tuple[str, str, str]:
        """
        Generates filename to save file locally by replacing chars in the title that are not:
        \\w(regex) - , . _ [ ] or a whitespace(" ")
        with an underscore and limiting its length. If file exists it adds a number padded
        to a width of 2 starting at one till there is no file with that name

        :param file_index: When part of a FileCollection and the files should be numbered
                           0 means no numbering
        :param subpath: relative to gwaripper_root/author/
        :return: Tuple of subpath(for non-audio file collections >=3 files), filename and
                 extension
        """

        title = []
        # always save everything in at most one sub-directory
        # even if further FileCollections would have a subpath
        # NOTE: IMPORTANT! if we change this behaviour also change
        # :PassSubpathSelftext
        subpath = top_parent.subpath if top_parent is not None else ""
        if self.parent:
            # reddit_title can only be a RedditInfo.title
            # but parent_title can also be a RedditInfo.title
            parent_title = self.parent.title if self.parent.title else self.parent.id
            if subpath:
                # only append parent_title if it's not also the top_parent
                if parent_title and self.parent is not top_parent:
                    title.append(parent_title[:30])
            else:
                # other FileCollections can't be >=3 files since then we'd have a subpath
                if top_parent and top_parent.title:
                    title.append(top_parent.title[:70])
                # include parent_title if we're not in a parent's subpath
                # and if top_parent is not our direct parent
                if parent_title and self.parent is not top_parent:
                    title.append(parent_title[:30])

        # file index and file title are always last
        if file_index:
            title.append(f"{file_index:02d}")
        title.append(self.title or self.id or "unnamed")
        # mypy doesn't allow re-definition of variables by default
        # since in python re-using the same variable doesn't avoid the allocation
        # contrary to statically compiled it will not save an allocation
        # function locals are just stored as pointers in an array for the function's scope
        # see https://docs.python-guide.org/writing/structure/#dynamic-typing
        # Variables are not a segment of the computer’s memory where some value
        # is written, they are ‘tags’ or ‘names’ pointing to objects.
        # Some guidelines help to avoid this issue:
        # - Avoid using the same variable name for different things.
        # - It is better to use different names even for things that are related,
        #   when they have a different type
        #   There is no efficiency gain when reusing names: the assignments
        #   will have to create new objects anyway
        title_combined: str = "_".join(s.strip() for s in title)

        filename = sanitize_filename(subpath, title_combined)
        return (subpath, filename, self.ext)


def parent_iter(start: Union[FileInfo, 'FileCollection']):
    p = start
    while True:
        if not p.parent:
            break
        yield p.parent
        p = p.parent


class FileCollection:

    def __init__(self, extractor: Type['BaseExtractor'], url: str, _id: Optional[str],
                 title: Optional[str], author: Optional[str],
                 children: Optional[List[Union[FileInfo, 'FileCollection']]] = None):
        self.extractor = extractor
        self.url = url
        self.id = _id
        self.title = title
        self.author = author
        # whether the FileCollection contains audio files; only FileCollection
        # with has_audio==True will be added to the DB
        self.has_audio = False
        # NOTE: will be set by _add_to_db_collection
        self.id_in_db: Optional[int] = None

        if children is None:
            self._children = []
        else:
            self._children = children

        # handled by property: returns empty string when there are not enough files to
        # have a subpath
        # NOTE: IMPORTANT folder names must not begin or end in spaces
        # so use strip or sanitize_filename; strip is enough here
        # since subpath uses sanitize_filename anyway
        self._subpath: str = self._update_subpath()
        self._nr_files: int = sum(1 for _, _ in
                                  children_iter_dfs(self._children, file_info_only=True))

        self._parent: Optional[FileCollection] = None
        # NOTE: a collection only counts as downloaded if all of it's children were downloaded
        # (including previous runs/already downloaded children)
        self._downloaded: DownloadErrorCode = DownloadErrorCode.COLLECTION_INCOMPLETE
        self.report: Optional[ExtractorReport] = None

    def __str__(self):
        return f"FileCollection<{self.url}, children: {self.nr_files}>"

    def _update_subpath(self) -> str:
        subpath = sanitize_filename(
                "", f"{self.title if self.title else self.id}")[:70].strip()
        self._subpath = subpath
        return subpath

    @property
    def children(self) -> List[Union[FileInfo, 'FileCollection']]:
        return self._children

    @property
    def nr_files(self) -> int:
        return self._nr_files

    @nr_files.setter
    def nr_files(self, value: int):
        delta = value - self.nr_files
        self._nr_files = value
        if self.parent:
            self.parent.nr_files += delta

    def add_file(self, info: FileInfo) -> None:
        # if an audio file gets added, this FileCollection as well as all its
        # parents need to be marked accordingly
        if not self.has_audio and info.is_audio:
            self.has_audio = True
            for parent in parent_iter(self):
                parent.has_audio = True

        self._children.append(info)
        info.parent = self

        self.nr_files += 1

        # TODO handle downloaded and already_downloaded here and in add_collection?

    def add_collection(self, collection: 'FileCollection'):
        # if a collection that contains audio files gets added, this FileCollection as well
        # as all its parents need to be marked accordingly
        if not self.has_audio and collection.has_audio:
            self.has_audio = True
            for parent in parent_iter(self):
                parent.has_audio = True
        self._children.append(collection)
        collection.parent = self
        self.nr_files += collection.nr_files

    @property
    def subpath(self) -> str:
        if self.nr_files >= 3:
            return self._subpath
        else:
            return ""

    # @CleanUp this is clunky
    @property
    def full_url(self):
        return self.url

    @property
    def downloaded(self):
        return self._downloaded

    @downloaded.setter
    def downloaded(self, value: DownloadErrorCode):
        self._downloaded = value
        if self.report is not None:
            self.report.download_error_code = value

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent: 'FileCollection'):
        self._set_parent(parent)

    # used so this can be called easily from subclasses
    def _set_parent(self, parent: 'FileCollection'):
        self._parent = parent

        if isinstance(parent, RedditInfo):
            # NOTE: set reddit_info on all children when parent gets set
            for child in cast(List[FileInfo], self.children):
                child.reddit_info = parent

    def get_preferred_author_name(self) -> str:
        names = [self.author]

        # bfs yields the names in level order level0 then level1 etc.
        for _, child in children_iter_bfs(self.children, file_info_only=False):
            # NOTE: since we allow nested FileCollections now and we still want
            # prioritize reddit author names we have to prepend reddit info authors
            if isinstance(child, RedditInfo):
                names.insert(0, child.author)
            else:
                names.append(child.author)

        # @Hack
        names.append(DELETED_USR_FOLDER if isinstance(self, RedditInfo) else None)
        names.append(UNKNOWN_USR_FOLDER)

        # preferred_author_name determines subfolder that the file gets save in
        # return DELETED_USR_FOLDER if neither RedditInfo or parent author nor the files
        # author is known
        # no reddit_info and no known author -> unkown user
        return [n for n in names if n][0]


class RedditInfo(FileCollection):

    # title of super class' type was inferred from __init__ parameters
    # You can declare types of variables in the class body explicitly using a
    # type annotation
    # overwrite base class Optional[str] type for title
    title: str
    # if a title should be a class variable use title: ClassVar[str] instead
    # then mypy checks if that attribute gets assigned using the instance
    # and warns you

    # can't redefine types of variables that were already defined in a base class
    # because then the expectation/promise of the derived class having at least
    # the same (type inlcuded when checked like it is here with mypy or in a
    # statically compiled language) attributes and methods as the base class
    # RedditInfo having a different type for attribute children would mean
    # we can't just create a function that takes FileCollection as a parameter
    # since it would suddenly be confronted with different types that the base
    # class didn't allow and our function obviously doesn't expect
    # NOTE not allowed: children: List[Union[FileInfo, 'FileCollection']]

    # a reddit submission (reddit's side) always has an id and a title
    # author might have been deleted
    def __init__(self, extractor: Type['BaseExtractor'], url: str, _id: str,
                 title: str, author: Optional[str], subreddit: str, permalink: str,
                 created_utc: float,
                 children: Optional[List[Union[FileInfo, 'FileCollection']]] = None):
        super().__init__(extractor, url, _id, title, author, children)

        self.permalink = permalink
        self.created_utc = created_utc
        self.subreddit: str = subreddit
        self.selftext: Optional[str] = None
        self.r_post_url: Optional[str] = None

    def __str__(self):
        return f"RedditInfo<{self.url}, children: {len(self.children)}>"

    # override base class implementation to disallow recursive RedditInfos
    def _set_parent(self, parent: 'FileCollection'):
        if isinstance(parent, RedditInfo):
            raise Exception("RedditInfo is not allowed to contain other RedditInfos!")
        else:
            super()._set_parent(parent)

    @property
    def full_url(self):
        return f"https://www.reddit.com{self.permalink}"

    def write_selftext_file(self, root_dir: str, subpath: str, force_path: bool = False):
        """
        Write selftext to a text file if not None
        Doesnt overwrite already existing selftext file!

        :param root_dir: Absolute path to GWARipper root
        :param user_path: Relative path from root_dir to subfolder where files of
                          RedditInfo collection are stored
        :param force_path: Use passed in :subpath: as base for the selftext filename
        :return: None
        """
        if not self.selftext:
            return None

        if force_path:
            selftext_fn = os.path.join(root_dir, f"{subpath}.txt")
        else:
            filename = sanitize_filename(subpath, self.title)
            # path.join works with joining empty strings
            filename = os.path.join(root_dir, subpath, filename)
            selftext_fn = f"{filename}.txt"

        if not os.path.isfile(selftext_fn):
            # create path since user might have downloaded the file and the moved it
            # to e.g. a backup
            os.makedirs(os.path.dirname(selftext_fn), exist_ok=True)
            with open(selftext_fn, "w", encoding="UTF-8") as w:
                w.write(f"Title: {self.title}\nPermalink: {self.permalink}\n"
                        f"Selftext:\n\n{self.selftext}")
