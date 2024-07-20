import os
import sys

import praw

MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..')))

import gwaripper.download as dl
import gwaripper.config as cfg
import gwaripper.gwaripper as gwa

from gwaripper.extractors.base import ExtractorErrorCode
from gwaripper.logging_setup import configure_logging
from gwaripper.reddit import reddit_praw



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

    sub = praw.models.Submission(reddit, id=row['id_on_page'])
    with g.db_con:
        flair_id = None
        if sub.link_flair_text:
            flair_id = g._get_flair_id(sub.link_flair_text)

        print(f"Upd Sub<{row['id_on_page']}> flair: {sub.link_flair_text} upvotes: {sub.score} self: {bool(sub.selftext)}")

        c.execute("""
            UPDATE RedditInfo SET
                upvotes = ?,
                flair_id = ?,
                selftext = ?
            WHERE id = ?
        """, (sub.score, flair_id, sub.selftext or None, entry.reddit_info_id))
