import os
import sys

import praw

import gwaripper.download as dl
import gwaripper.config as cfg
import gwaripper.gwaripper as gwa

from gwaripper.extractors.base import ExtractorErrorCode
from gwaripper.logging_setup import configure_logging
from gwaripper.reddit import reddit_praw

MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..')))


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
SELECT * FROM FileCollection
WHERE FileCollection.url LIKE "%reddit.com%"
""").fetchall()

root = cfg.get_root()
configure_logging(os.path.join(root, "gwaripper_populate_extended_ri.log"))

reddit = reddit_praw()

for row in rows:
    entry = RowHelper(row)

    if entry.reddit_info_id is None:
        continue

    praw.models.Submission()
