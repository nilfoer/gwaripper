import datetime
import sqlite3

date = '2020-11-07'


def upgrade(db_con):
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    c.execute("ALTER TABLE Downloads RENAME TO temp")
    c.execute("DROP TABLE Downloads_fts_idx")
    c.execute("DROP TRIGGER Downloads_ai")
    c.execute("DROP TRIGGER Downloads_ad")
    c.execute("DROP TRIGGER Downloads_au")

    c.execute("""CREATE TABLE IF NOT EXISTS Downloads(
                   id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT,
                   description TEXT, local_filename TEXT, title TEXT,
                   url_file TEXT, url TEXT, created_utc REAL,
                   r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,
                   reddit_url TEXT, reddit_user TEXT,
                   author_page TEXT, author_subdir TEXT NOT NULL, subreddit_name TEXT,
                   rating REAL, favorite INTEGER NOT NULL DEFAULT 0)""")

    c.execute("""
    -- full text-search virtual table
    -- only stores the idx due to using parameter content='..'
    -- -> external content table
    -- but then we have to keep the content table and the idx up-to-date ourselves
    CREATE VIRTUAL TABLE IF NOT EXISTS Downloads_fts_idx USING fts5(
      title, reddit_title, content='Downloads', content_rowid='id')""")

    c.execute("""-- Triggers to keep the FTS index up to date.
                 CREATE TRIGGER IF NOT EXISTS Downloads_ai AFTER INSERT ON Downloads BEGIN
                   INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
                   VALUES (new.id, new.title, new.reddit_title);
                 END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS Downloads_ad AFTER DELETE ON Downloads BEGIN
                   INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
                   VALUES('delete', old.id, old.title, old.reddit_title);
                 END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS Downloads_au AFTER UPDATE ON Downloads BEGIN
                   INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
                   VALUES('delete', old.id, old.title, old.reddit_title);
                   INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
                   VALUES (new.id, new.title, new.reddit_title);
                 END""")

    rows = c.execute("SELECT * FROM temp").fetchall()

    for r in rows:
        reddit_user = r['reddit_user']
        author_subdir = r['sgasm_user']
        # old version uses sgasm_user as subdir for all files
        # v0.3 uses reddit_user if the audio url was parsed from a submission
        # otherwise it uses sgasm_user or the author of the containing FileCollection
        # which should not exist (currently no extractor (but reddit) returns a FileCollection
        # that contains audio files
        # compare v0.3-alpha release date -> older use reddit_user as author_subdir
        date_str = r['date']
        try:
            date = None if date_str is None else (
                    datetime.datetime.strptime(date_str, '%Y-%m-%d'))
        except ValueError:
            date = None
        if (reddit_user and date is not None and
                date > datetime.datetime(year=2020, month=10, day=10)):
            author_subdir = reddit_user

        val_dict = {k: r[k] for k in r.keys()}
        val_dict['author_page'] = r['sgasm_user']
        val_dict['author_subdir'] = author_subdir
        c.execute("""
        INSERT INTO Downloads(
            id, date, time, description, local_filename, title, url_file, url, created_utc,
            r_post_url, reddit_id, reddit_title, reddit_url, reddit_user, author_page,
            author_subdir, subreddit_name, rating, favorite)
        VALUES(
            :id, :date, :time, :description, :local_filename, :title, :url_file, :url,
            :created_utc, :r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user,
            :author_page, :author_subdir, :subreddit_name, :rating, :favorite)""", val_dict)

    c.execute("DROP TABLE temp")
