import sys
import os
import urllib.request
import urllib.error
import logging

from typing import Optional, Dict
from urllib.error import ContentTooShortError

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
    }


def download(url: str, dl_path: str):
    """
    Will download the file to dl_path, return True on success

    :param curfnr: Current file number
    :param maxfnr: Max files to download
    :return: Current file nr(int)
    """
    # get head (everythin b4 last part of path ("/" last -> tail empty,
    # filename or dir(without /) -> tail)) of path; no slash in path -> head empty
    dirpath, fn = os.path.split(dl_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    try:
        _, headers = urllib.request.urlretrieve(url, dl_path)  # reporthook=prog_bar_dl)
    except urllib.error.HTTPError as err:
        # catch this more detailed first then broader one (HTTPError is subclass of URLError)
        logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        return False, None
    except urllib.error.URLError as err:
        logger.warning("URL Error %s: \"%s\"", err.reason, url)
        return False, None
    else:
        return True, headers


def download_in_chunks(url: str, filename: str,
                       headers: Optional[Dict[str, str]] = None,
                       prog_bar: bool = False) -> int:
    # get head (everythin b4 last part of path ("/" last -> tail empty,
    # filename or dir(without /) -> tail)) of path; no slash in path -> head empty
    dirpath, fn = os.path.split(filename)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    req = urllib.request.Request(url, headers=DEFAULT_HEADERS if headers is None else headers)
    # urlretrieve uses block-size of 8192
    # Before response.read() is called, the contents are not downloaded.
    with urllib.request.urlopen(req) as response:
        meta = response.info()
        reported_file_size = int(meta["Content-Length"])
        # by Alex Martelli
        # Experiment a bit with various CHUNK sizes to find the "sweet spot" for your requirements
        # CHUNK = 16 * 1024
        file_size_dl = 0
        chunk_size = 8192
        block_num = 0
        with open(filename, 'wb') as w:
            while True:
                chunk = response.read(chunk_size)

                if not chunk:
                    break

                # not chunk_size since the last chunk will probably not be of size chunk_size
                file_size_dl += len(chunk)
                w.write(chunk)
                block_num += 1
                # copy behaviour of urlretrieve reporthook
                if prog_bar:
                    prog_bar_dl(block_num, chunk_size, reported_file_size)

    # from urlretrieve doc: urlretrieve() will raise ContentTooShortError when
    # it detects that the amount of data available was less than the expected
    # amount (which is the size reported by a Content-Length header). This can
    # occur, for example, when the download is interrupted.
    # The Content-Length is treated as a lower bound: if there’s more data to
    # read, urlretrieve reads more data, but if less data is available, it
    # raises the exception.
    if file_size_dl < reported_file_size:
        raise ContentTooShortError(
                f"Downloaded file's size is samller than the reported size for \"{url}\"",
                None)
    else:
        return file_size_dl


def get_url_file_size(url: str) -> int:
    """Returns file size in bytes that is reported in Content-Length Header"""
    with urllib.request.urlopen(url) as response:
        reported_file_size = int(response.info()["Content-Length"])
    return reported_file_size


def prog_bar_dl(blocknum: int, blocksize: int, totalsize: int) -> None:
    """
    Displays a progress bar to sys.stdout

    blocknum * blocksize == bytes read so far
    Only display MB read when total size is -1
    Calc percentage of file download, number of blocks to display is bar length * percent/100
    String to display is Downloading: xx.x% [#*block_nr + "-"*(bar_len-block_nr)] xx.xx MB

    http://stackoverflow.com/questions/13881092/download-progressbar-for-python-3
    by J.F. Sebastian
    combined with:
    http://stackoverflow.com/questions/3160699/python-progress-bar
    by Brian Khuu
    and modified

    :param blocknum: Count of blocks transferred so far
    :param blocksize: Block size in bytes
    :param totalsize: Total size of the file in bytes
    :return: None
    """
    bar_len = 25  # Modify this to change the length of the progress bar
    # blocknum is current block, blocksize the size of each block in bytes
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize  # 1e2 == 100.0
        # nr of blocks
        block_nr = int(round(bar_len*readsofar/totalsize))
        # %5.1f: pad to 5 chars and display one decimal, type float, %% -> escaped %sign
        # %*d -> Parametrized, width -> len(str(totalsize)), value -> readsofar
        # s = "\rDownloading: %5.1f%% %*d / %d" % (percent, len(str(totalsize)), readsofar, totalsize)
        sn = "\rDownloading: {:4.1f}% [{}] {:4.2f} / {:.2f} MB".format(percent, "#"*block_nr + "-"*(bar_len-block_nr),
                                                                       readsofar / 1024**2, totalsize / 1024**2)
        sys.stdout.write(sn)
        if readsofar >= totalsize:  # near the end
            sys.stdout.write("\n")
    else:  # total size is unknown
        sys.stdout.write("\rDownloading: %.2f MB" % (readsofar / 1024**2,))
    # Python's standard out is buffered (meaning that it collects some of the data "written" to standard out before
    # it writes it to the terminal). flush() forces it to "flush" the buffer, meaning that it will write everything
    # in the buffer to the terminal, even if normally it would wait before doing so.
    sys.stdout.flush()


