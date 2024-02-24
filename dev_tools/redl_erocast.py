import os
import sys

MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..')))
import gwaripper.gwaripper as gwa
import gwaripper.config as cfg
import gwaripper.download as dl

from gwaripper.logging_setup import configure_logging
from gwaripper.extractors.base import ExtractorErrorCode
from gwaripper.extractors.erocast import ErocastExtractor


class RowHelper:
    def __init__(self, row):
        self._row = row

    def __getattr__(self, name: str):
        try:
            return self._row[name]
        except (IndexError, KeyError):
            print("Key", name, "not found")
            raise


g = gwa.GWARipper()
c = g.db_con.cursor()
rows = c.execute("""
SELECT
	a.collection_id,
	a.filename,
	a.title,
	a.url,
	Alias.name as alias_name,
	fc.title AS collection_title,
	fc.subpath,
	(SELECT name FROM Alias WHERE id = fc.alias_id) AS fc_alias
FROM AudioFile a
LEFT JOIN Alias ON a.alias_id = Alias.id
LEFT JOIN FileCollection fc ON a.collection_id = fc.id
WHERE a.url LIKE '%erocast.me%' 
""").fetchall()

root = cfg.get_root()
configure_logging(os.path.join(root, "gwaripper_redl.log"))

successful_redls_txt = os.path.join(root, 'redl_erocast.txt')
if os.path.isfile(successful_redls_txt):
    with open(successful_redls_txt, 'r', encoding='utf-8') as f:
        successful_redls = set(f.strip() for f in f.readlines())
else:
    successful_redls = set()


for row in rows:
    entry = RowHelper(row)

    # we might crash and don't want to re-dl successful_redls
    if entry.url in successful_redls:
        print("Skipping redled url", entry.url)
        continue

    if entry.collection_id is not None:
        author_subdir = entry.fc_alias
        subpath = entry.subpath
    else:
        author_subdir = entry.alias_name
        subpath = ""

    dirpath = os.path.join(author_subdir, subpath)
    os.makedirs(os.path.join(root, dirpath), exist_ok=True)
    fn, ext = entry.filename.rsplit('.', 1)
    redl_fn = f'{fn}_redl.{ext}'
    redl_rel_path = os.path.join(dirpath, redl_fn)
    redl_full_path = os.path.join(root, redl_rel_path)

    info, extr_report = ErocastExtractor(entry.url)._extract()
    if info is None or extr_report.err_code != ExtractorErrorCode.NO_ERRORS:
        print("EXTRACTOR ERROR:", extr_report.err_code)
        continue
    # DL
    print("Downloading", info.page_url, "to", redl_rel_path)
    success = dl.download_hls_ffmpeg(info.direct_url, redl_full_path)
    if not success:
        print("Download FAILED!")
        continue

    with open(successful_redls_txt, 'a', encoding='utf-8') as f:
        f.write(entry.url + "\n")

    orig_full_path = os.path.join(root, dirpath, entry.filename)
    stat_new = os.stat(redl_full_path)
    try:
        stat_old = os.stat(orig_full_path)
    except FileNotFoundError:
        stat_old = os.stat_result((0,) * 10)

    if stat_new.st_size > stat_old.st_size:
        print("Replacing orig with redl for", entry.filename)
        try:
            os.remove(orig_full_path)
        except FileNotFoundError:
            pass
        os.rename(redl_full_path, orig_full_path)
