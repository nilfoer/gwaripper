import os
import urllib.request
import logging

logger = logging.getLogger(__name__)


def download(url, dl_path):
    """
    Will download the file to dl_path, return True on success

    :param curfnr: Current file number
    :param maxfnr: Max files to download
    :return: Current file nr(int)
    """
    # get head (everythin b4 last part of path ("/" last -> tail empty, filename or dir(without /) -> tail)) of path; no slash in path -> head empty
    dirpath, fn = os.path.split(dl_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    try:
        _, headers = urllib.request.urlretrieve(url, dl_path)  # reporthook=prog_bar_dl)
    except urllib.request.HTTPError as err:
        # catch this more detailed first then broader one (HTTPError is subclass of URLError)
        logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        return False, None
    except urllib.request.URLError as err:
        logger.warning("URL Error %s: \"%s\"", err.reason, url)
        return False, None
    else:
        return True, headers


def download_in_chunks(url, filename):
    # get head (everythin b4 last part of path ("/" last -> tail empty, filename or dir(without /) -> tail)) of path; no slash in path -> head empty
    dirpath, fn = os.path.split(filename)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    # urlretrieve uses block-size of 8192
    # Before response.read() is called, the contents are not downloaded.
    with urllib.request.urlopen(url) as response:
        meta = response.info()
        reported_file_size = int(meta["Content-Length"])
        # by Alex Martelli
        # Experiment a bit with various CHUNK sizes to find the "sweet spot" for your requirements
        # CHUNK = 16 * 1024
        file_size_dl = 0
        chunk_size = 8192
        with open(filename, 'wb') as w:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break

                # not chunk_size since the last chunk will probably not be of size chunk_size
                file_size_dl += len(chunk)
                w.write(chunk)

    # from urlretrieve doc: urlretrieve() will raise ContentTooShortError when it detects that the amount of data available was less than the expected amount (which is the size reported by a Content-Length header). This can occur, for example, when the download is interrupted.
    # The Content-Length is treated as a lower bound: if there’s more data to read, urlretrieve reads more data, but if less data is available, it raises the exception.
    if file_size_dl < reported_file_size:
        logger.warning("Downloaded file's size is samller than the reported size for "
                       "\"%s\"", url)
        return False, file_size_dl
    else:
        return True, file_size_dl


def get_url_file_size(url):
    """Returns file size in bytes that is reported in Content-Length Header"""
    with urllib.request.urlopen(url) as response:
        reported_file_size = int(response.info()["Content-Length"])
    return reported_file_size
