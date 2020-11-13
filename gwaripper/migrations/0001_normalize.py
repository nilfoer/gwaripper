import os
import datetime
import sqlite3
import logging
import re

from .. import config

date = '2020-11-08'

logger = logging.getLogger(__name__)

FILENAME_MAX_LEN = 185
DELETED_USR_FOLDER = "deleted_users"
UNKNOWN_USR_FOLDER = "_unknown_user_files"


def sanitize_filename(subpath: str, filename: str):
    # folder names must not start or end with spaces
    assert subpath.strip() == subpath
    # [^\w\-_\.,\[\] ] -> match not(^) any of \w \- _  and whitepsace etc.,
    # replace any that isnt in the  [] with _
    chars_remaining = FILENAME_MAX_LEN - len(subpath)
    assert chars_remaining >= 30
    return re.sub(r"[^\w\-_.,\[\] ]", "_", filename.strip()[:chars_remaining].strip())


def date_str_to_date(date_str: str) -> datetime.date:
    try:
        # important that all dates are of type date and not datetime since
        # you can't compare the two
        date = datetime.date(year=2000, month=1, day=1) if date_str is None else (
                datetime.datetime.strptime(date_str, '%Y-%m-%d').date())
    except ValueError:
        date = datetime.date(year=2000, month=1, day=1)
    return date


def combine_duplicate_url(c):
    # get duplicate urls
    # some (from very old version) rows only have url_file
    rows = c.execute("""
    --SELECT url FROM Downloads WHERE url IS NOT NULL GROUP BY url HAVING count(*) > 1
    --UNION
    --SELECT url_file FROM Downloads WHERE url IS NULL GROUP BY url_file HAVING count(*) > 1
    --ORDER BY url
    -- could either select all url or url_file and then query for that
    -- or use the group by that we're doing anyway to get all the ids
    -- using aggregate funciton group_concat and then later just
    -- getting the rows by id
    SELECT group_concat(id, ',') as ids FROM Downloads WHERE url IS NOT NULL
    GROUP BY url HAVING count(*) > 1
    UNION
    SELECT group_concat(id, ',') as ids FROM Downloads WHERE url IS NULL
    GROUP BY url_file HAVING count(*) > 1
    """).fetchall()
    #print("\n".join(f"{url[0]}" for url in rows))

    for r in rows:
        duplicate_row_ids = [int(i) for i in r[0].split(',')]
        c.execute(f"""
        SELECT * FROM Downloads
        WHERE id IN ({','.join('?' for _ in range(len(duplicate_row_ids)))})
        ORDER BY id""", duplicate_row_ids)
        duplicate_rows = c.fetchall()
        assert len(duplicate_rows) > 1
        # keep latest / greatest id
        keep = duplicate_rows[-1]
        del duplicate_rows[-1]
        diffs = []
        update_dict = {}
        for row in duplicate_rows:
            for k in keep.keys():
                if k == 'id':
                    continue
                # for logging diffs
                if row[k] and k not in ('date', 'time') and keep[k] != row[k]:
                    diffs.append(f"Keep[{k}] = {keep[k]}")
                    diffs.append(f"Del[{k}] = {row[k]}")
                # the row we want to keep has no value set but this one has
                if not keep[k] and row[k]:
                    # later rows might overwrite this but we prioritize rows that
                    # were added later (and thats the order of our iteration)
                    update_dict[k] = row[k]

            # DEL ROW!!
            c.execute("DELETE FROM Downloads WHERE id = ?", (row['id'],))

        if diffs:
            logger.info("Title: %s by %s\n%s\n\n", keep['title'], keep['author_page'],
                        '\n'.join(diffs))

        if update_dict:
            upd_cols = [f"{col} = :{col}" for col in update_dict]
            update_dict['id'] = keep['id']
            c.execute(f"""
            UPDATE Downloads SET
                {', '.join(col_set_stmt for col_set_stmt in upd_cols)}
            WHERE id = :id""", update_dict)


def upgrade(db_con):
    # NOTE: don't use imported code here otherwise changes to that code
    # might break the migration!
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    combine_duplicate_url(c)

    c.execute("ALTER TABLE Downloads RENAME TO temp")
    c.execute("DROP TABLE Downloads_fts_idx")
    c.execute("DROP TRIGGER Downloads_ai")
    c.execute("DROP TRIGGER Downloads_ad")
    c.execute("DROP TRIGGER Downloads_au")

    create_tables(c)

    rows = c.execute("SELECT * FROM temp").fetchall()

    # keep track of rowids for inserted filecollections and aliases so we don't
    # have to query for them
    # reddit is the only filecol currently tracked in db since it's the only
    # that con contain audio files
    reddit_id_collection_id = {}
    alias_name_rowid_artist_set = {}

    c.execute("INSERT OR IGNORE INTO Alias(name) VALUES (?)", (DELETED_USR_FOLDER,))
    alias_name_rowid_artist_set[DELETED_USR_FOLDER] = (c.lastrowid, True)
    c.execute("INSERT OR IGNORE INTO Alias(name) VALUES (?)", (UNKNOWN_USR_FOLDER,))
    alias_name_rowid_artist_set[UNKNOWN_USR_FOLDER] = (c.lastrowid, True)

    for r in rows:
        date = date_str_to_date(r['date'])

        reddit_user = r['reddit_user']
        reddit_id = r['reddit_id']
        alias = r['author_page']
        alias = alias.strip() if alias is not None else alias
        reddit_user_set = False
        if (not reddit_user or reddit_user == 'None') and reddit_id:
            # reddit info but we have a deleted user
            reddit_user = DELETED_USR_FOLDER
        elif reddit_user:
            c.execute("INSERT OR IGNORE INTO Artist(name) VALUES (?)", (reddit_user,))
            reddit_user_set = True

        # use a function since we have to do this 2 times: once for author_page
        # and once for reddit_user
        # save if we set an artist so we can update an alias' artist if we later
        # do have the reddit info for that
        def get_or_create_alias(name):
            try:
                alias_id, artist_set = alias_name_rowid_artist_set[name]
                if not artist_set and reddit_user_set:
                    c.execute("""UPDATE Alias SET
                                    artist_id = (SELECT Artist.id FROM Artist WHERE name = ?)
                                 WHERE Alias.id = ?""", (reddit_user, alias_id))
            except KeyError:
                c.execute("""INSERT INTO Alias(artist_id, name) VALUES (
                             (SELECT id FROM Artist WHERE name = ?), ?)""",
                          (reddit_user, name))
                alias_id = c.lastrowid
                alias_name_rowid_artist_set[name] = (c.lastrowid, reddit_user_set)
            return alias_id

        if not alias:
            if reddit_user:
                alias = reddit_user
            else:
                alias = UNKNOWN_USR_FOLDER
        alias_id = get_or_create_alias(alias)

        collection_id = None
        if reddit_id:
            try:
                collection_id = reddit_id_collection_id[reddit_id]
            except KeyError:
                reddit_user_alias_id = get_or_create_alias(reddit_user) if reddit_user else None
                submission_self_url = r['reddit_url']
                if submission_self_url.startswith('http'):
                    submission_self_url = submission_self_url.replace('http:', 'https:')
                else:
                    submission_self_url = f"https://www.reddit.com{submission_self_url}"

                subpath = ""
                # <v0.3 won't have a subpath
                if date > datetime.date(year=2020, month=10, day=10):
                    #
                    # re-create subpath that was not added to DB previously due to a bug
                    #
                    nr_files_row = c.execute("SELECT count(*) FROM temp WHERE reddit_id = ?",
                                             (reddit_id,)).fetchone()
                    nr_files = int(nr_files_row[0])

                    # since we don't add non-audio files to the DB we might have more files
                    # than nr_files and thus have a subpath
                    # -> test if the file exists without else assume a subpath
                    # user might have moved file to a backup but that's the best we can do
                    file_without_subpath = os.path.join(config.get_root(),
                                                        r['author_subdir'],
                                                        r['local_filename'])
                    file_found_without_subpath = os.path.isfile(file_without_subpath)

                    if nr_files >= 3 or not file_found_without_subpath:
                        subpath = sanitize_filename("", r['reddit_title'])[:70].strip()

                c.execute("INSERT INTO RedditInfo(created_utc) VALUES (?)",
                          (r['created_utc'],))
                reddit_info_id = c.lastrowid

                file_collection_dict = {
                    "url": submission_self_url,
                    "id_on_page": reddit_id,
                    "title": r['reddit_title'],
                    "subpath": subpath,
                    "reddit_info_id": reddit_info_id,
                    # RedditInfo can't have a parent
                    "parent_id": None,
                    "alias_id": reddit_user_alias_id
                }

                c.execute("""
                INSERT INTO FileCollection(
                    url, id_on_page, title, subpath, reddit_info_id, parent_id, alias_id
                )
                VALUES (
                    :url, :id_on_page, :title, :subpath, :reddit_info_id, :parent_id, :alias_id
                )
                """, file_collection_dict)

                collection_id = c.lastrowid
                reddit_id_collection_id[reddit_id] = c.lastrowid

        filename = r['local_filename']
        filename = filename if filename else ''
        audio_file_dict = {
            "id": r['id'],
            "collection_id": collection_id,
            "downloaded_with_collection": 1 if collection_id is not None else 0,
            "date": date,
            "description": r['description'],
            "filename": filename,
            "title": r['title'],
            "url": r['url'] if r['url'] else r['url_file'],
            "alias_id": alias_id,
            "rating": r['rating'],
            "favorite": r['favorite']
        }

        try:
            c.execute("""
            INSERT INTO AudioFile(
                id, collection_id, downloaded_with_collection, date, description,
                filename, title, url, alias_id, rating, favorite
            )
            VALUES(
                :id, :collection_id, :downloaded_with_collection, :date, :description,
                :filename, :title, :url, :alias_id, :rating, :favorite
            )""", audio_file_dict)
        except sqlite3.IntegrityError as err:
            if "UNIQUE constraint failed" in str(err):
                print("Skipped unhandled duplicate AudioFile with URL:", audio_file_dict['url'])
            else:
                raise

    c.execute("DROP TABLE temp")


def create_tables(c):
    c.execute("PRAGMA foreign_keys=off")
    c.execute("""
    CREATE TABLE AudioFile(
        id INTEGER PRIMARY KEY ASC,
        collection_id INTEGER,
        downloaded_with_collection INTEGER NOT NULL DEFAULT 0,
        date DATE NOT NULL,
        -- removed: time TEXT,
        description TEXT,
        filename TEXT NOT NULL,
        title TEXT,
        -- removed: url_file TEXT,
        url TEXT UNIQUE NOT NULL,
        alias_id INTEGER NOT NULL,
        rating REAL,
        favorite INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (collection_id) REFERENCES FileCollection(id)
          -- can't delete a FileCollection if there are still rows with
          -- it's id as collection_id here
          ON DELETE RESTRICT,
        FOREIGN KEY (alias_id) REFERENCES Alias(id)
          ON DELETE RESTRICT
    )""")

    c.execute("CREATE INDEX audio_file_collection_id_idx ON AudioFile(collection_id)")
    c.execute("CREATE INDEX audio_file_alias_id_idx ON AudioFile(alias_id)")

    # so we can match aliases to an artist and use the artist name for displaying
    # all the files of it's aliases
    # files will still be stored under the alias name though since if we don't have
    # reddit information we can't match an audio host user name (alias) to an artist
    # without user interaction and we also can't match on similarity
    # matching later when we have reddit info that links an alias an artist is also
    # not an option since we'd have to move the files which might not be present
    # anymore (e.g. backed up somewhere else)
    c.execute("""
    CREATE TABLE Artist(
        id INTEGER PRIMARY KEY ASC,
        name TEXT UNIQUE NOT NULL
    )""")

    c.execute("""
    CREATE TABLE Alias(
        id INTEGER PRIMARY KEY ASC,
        artist_id INTEGER,
        name TEXT UNIQUE NOT NULL,
        FOREIGN KEY (artist_id) REFERENCES Artist(id)
            ON DELETE RESTRICT
    )""")

    # Indexes are implicitly created only in the case of PRIMARY KEY and UNIQUE statements
    # so these are not needed
    # c.execute("CREATE UNIQUE INDEX alias_name_idx ON Alias(name)")
    # c.execute("CREATE UNIQUE INDEX artist_name_idx ON Artist(name)")
    # on foreign keys they are not created automatically
    c.execute("CREATE INDEX alias_artist_id_idx ON Alias(artist_id)")

    c.execute("""
    CREATE TABLE FileCollection(
        id INTEGER PRIMARY KEY ASC,
        url TEXT UNIQUE NOT NULL,
        id_on_page TEXT,
        title TEXT,
        subpath TEXT NOT NULL,
        reddit_info_id INTEGER,
        parent_id INTEGER,
        alias_id INTEGER NOT NULL,
        FOREIGN KEY (reddit_info_id) REFERENCES RedditInfo(id)
          ON DELETE RESTRICT,
        FOREIGN KEY (parent_id) REFERENCES FileCollection(id)
          ON DELETE RESTRICT,
        FOREIGN KEY (alias_id) REFERENCES Alias(id)
          ON DELETE RESTRICT
    )""")

    # we only need created_utc here (if at all) but put the structure in place anyway
    # since we might expand it later
    c.execute("""
    CREATE TABLE RedditInfo(
        id INTEGER PRIMARY KEY ASC,
        created_utc REAL
        -- basically a duplicate of the only AudioFile child's url
        -- removed since ^: r_post_url TEXT,  -- outgoing post url or link to self
        -- replaced by FileCollection.id_on_page: reddit_id TEXT,
        -- replaced by FileCollection.title: reddit_title TEXT,
        -- replaced by FileCollection.url: reddit_url TEXT,  -- permalink
        -- replaced by FileCollection.alias_id: reddit_user TEXT,
        -- could be extracted from url
        -- subreddit TEXT
        -- should we safe the selftext in the db?
        -- selftext TEXT
    )""")

    # https://stackoverflow.com/a/9282556 dave mankoff:
    # usually using views will have slightly less overhead as the query
    # parser/planner doesn't have to reparse the raw sql on each execution. It
    # can parse it once, store its execution strategy, and then use that each
    # time the query is actually run.
    #
    # The performance boost you see with this will generally be small, in the grand
    # scheme of things. It really only helps if its a fast query that you're
    # executing frequently. If its a slow query you execute infrequently, the
    # overhead associated with parsing the query is insignificant.
    c.execute("""
    CREATE VIEW v_audio_and_collection_combined
    AS
    SELECT
        AudioFile.id,
        AudioFile.collection_id,
        AudioFile.downloaded_with_collection,
        AudioFile.date,
        AudioFile.description,
        AudioFile.filename,
        AudioFile.title,
        AudioFile.url,
        AudioFile.alias_id,
        AudioFile.rating,
        AudioFile.favorite,
        Alias.name as alias_name,
        Artist.name as artist_name,
        FileCollection.id as fcol_id,
        FileCollection.url as fcol_url,
        FileCollection.id_on_page as fcol_id_on_page,
        FileCollection.title as fcol_title,
        FileCollection.subpath as fcol_subpath,
        FileCollection.reddit_info_id as fcol_reddit_info_id,
        FileCollection.parent_id as fcol_parent_id,
        FileCollection.alias_id as fcol_alias_id,
        -- get alias name for FileCollection
        -- artist_id of fcol and audiofile will be the same so we don't
        -- have to query for that
        (SELECT
                Alias.name
         FROM Alias WHERE Alias.id = FileCollection.alias_id) as fcol_alias_name,
        RedditInfo.created_utc as reddit_created_utc
    FROM AudioFile
    LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
    LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
    JOIN Alias ON Alias.id = AudioFile.alias_id
    LEFT JOIN Artist ON Artist.id = Alias.artist_id
    """)

    # NOTE: sql fts view testing code below; idea is that since we split up
    # title and collection/reddit_title into separate tables we'd
    # use a view as content table for the fts index using a LEFT JOIN
    #
    # this way would probably require more disk space since we're inserting the
    # collection title for every audio in a collection but since most collections
    # (5791 - 337/5791 in my db) only have one audio (avg 1.12) it's fine
    #
    # other solution would be to have two fts5 indices, do two separate queries
    # and then combine the result

    c.execute("""
    CREATE VIEW v_audio_and_collection_titles
    AS
    SELECT
        AudioFile.id as audio_id,
        FileCollection.title as collection_title,
        AudioFile.title as audio_title
    FROM AudioFile
    LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
    """)

    c.execute("""
    -- full text-search virtual table
    -- only stores the idx due to using parameter content='..'
    -- -> external content table (here using a view)
    -- but then we have to keep the content table and the idx up-to-date ourselves
    CREATE VIRTUAL TABLE IF NOT EXISTS Titles_fts_idx USING fts5(
      title, collection_title,
      content='v_audio_and_collection_titles',
      content_rowid='audio_id')""")

    # since if or case/when are only allowed to be used to select between other expressions
    # and not with INSERT:
    # use TRIGGER's WHEN condition and then create multiple triggers with that
    # c.execute("""-- Triggers to keep the FTS index up to date.
    # CREATE TRIGGER AudioFile_ai_with_collection AFTER INSERT ON AudioFile
    # WHEN new.collection_id IS NOT NULL
    # BEGIN
    #     INSERT INTO Titles_fts_idx(rowid, title, collection_title)
    #     VALUES (
    #         new.id,
    #         new.title,
    #         -- subquery for collection title
    #         (SELECT title FROM FileCollection WHERE id = new.collection_id)
    #     );
    # END""")
    # c.execute("""
    # CREATE TRIGGER AudioFile_ai_without_collection AFTER INSERT ON AudioFile
    # WHEN new.collection_id IS NULL
    # BEGIN
    #     INSERT INTO Titles_fts_idx(rowid, title, collection_title)
    #     VALUES (
    #         new.id,
    #         new.title,
    #         NULL
    #     );
    # END""")

    # in this case also possible using one trigger with case/when since we're
    # inserting into the same table etc.
    # WHEN NULL does not work it just appeared to work since the subquery
    # with WHERE FileCollection.id = NULL returned no rows which means NULL will
    # be inserted (which we could use but then the subquery would be run every time)
    # use WHEN new.collection_id IS NULL instead
    c.execute("""
    CREATE TRIGGER AudioFile_ai AFTER INSERT ON AudioFile
    BEGIN
        INSERT INTO Titles_fts_idx(rowid, title, collection_title)
        VALUES (
            new.id,
            new.title,
            (CASE
             WHEN new.collection_id IS NULL THEN NULL
             ELSE (SELECT title FROM FileCollection WHERE id = new.collection_id)
             END)
        );
    END
    """)
    # the values inserted into the other columns must match the values
    # currently stored in the table otherwise the results may be unpredictable
    c.execute("""
    CREATE TRIGGER AudioFile_ad AFTER DELETE ON AudioFile
    BEGIN
        INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, title, collection_title)
        VALUES(
            'delete',
            old.id,
            old.title,
            (CASE
             WHEN old.collection_id IS NULL THEN NULL
             ELSE (SELECT title FROM FileCollection WHERE id = old.collection_id)
             END)
        );
    END
    """)
    c.execute("""
    CREATE TRIGGER AudioFile_au AFTER UPDATE ON AudioFile
    BEGIN
        -- delete old entry
        INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, title, collection_title)
        VALUES(
            'delete',
            old.id,
            old.title,
            (CASE
             WHEN old.collection_id IS NULL THEN NULL
             ELSE (SELECT title FROM FileCollection WHERE id = old.collection_id)
             END)
        );
        -- insert new one
        INSERT INTO Titles_fts_idx(rowid, title, collection_title)
        VALUES (
            new.id,
            new.title,
            (CASE
             WHEN new.collection_id IS NULL THEN NULL
             ELSE (SELECT title FROM FileCollection WHERE id = new.collection_id)
             END)
        );
    END
    """)
    c.execute("PRAGMA foreign_keys=on")
