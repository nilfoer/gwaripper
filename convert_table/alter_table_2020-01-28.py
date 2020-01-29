import sqlite3

db_con = sqlite3.connect("./gwarip_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    # The "content" option may be used to create an FTS5 table that stores only
    # FTS full-text index entries. Because the column values themselves are
    # usually much larger than the associated full-text index entries, this can
    # save significant database space.
    # -> so we don't store long columns title and reddit_title 2x
    # It is still the responsibility of the user to ensure that the contents of
    # an external content FTS5 table are kept up to date with the content
    # table. One way to do this is with triggers. For example:
    c = db_con.executescript("""
        PRAGMA foreign_keys=off;

        BEGIN TRANSACTION;

        -- full text-search virtual table
        -- only stores the idx due to using parameter content='..'
        -- -> external content table
        -- but then we have to keep the content table and the idx up-to-date ourselves
        CREATE VIRTUAL TABLE IF NOT EXISTS Downloads_fts_idx USING fts5(
          title, reddit_title, content='Downloads', content_rowid='id');

        -- even as external content table creating the table is not  enough
        -- it needs to be manually populated from the content/original table
        INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
            SELECT id, title, reddit_title FROM Downloads;

        -- Triggers to keep the FTS index up to date.
        CREATE TRIGGER Downloads_ai AFTER INSERT ON Downloads BEGIN
          INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
          VALUES (new.id, new.title, new.reddit_title);
        END;
        CREATE TRIGGER Downloads_ad AFTER DELETE ON Downloads BEGIN
          INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
          VALUES('delete', old.id, old.title, old.reddit_title);
        END;
        CREATE TRIGGER Downloads_au AFTER UPDATE ON Downloads BEGIN
          INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
          VALUES('delete', old.id, old.title, old.reddit_title);
          INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
          VALUES (new.id, new.title, new.reddit_title);
        END;

        COMMIT;

        PRAGMA foreign_keys=on;""")
