import sqlite3

date = '2024-07-14'


def upgrade(db_con):
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    c.execute("DROP TRIGGER AudioFile_ai")
    c.execute("DROP TRIGGER AudioFile_au")
    c.execute("DROP TRIGGER AudioFile_ad")
    c.execute("DROP VIEW v_audio_and_collection_combined")
    c.execute("DROP VIEW v_audio_and_collection_titles")

    c.execute("ALTER TABLE RedditInfo RENAME TO ri_temp")
    c.execute("""
        CREATE TABLE Flair(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL
        )
        """)
    c.execute("""
        CREATE TABLE RedditInfo(
            id INTEGER PRIMARY KEY ASC,
            created_utc REAL,
            upvotes INTEGER,
            flair_id INTEGER,
            selftext TEXT,
            FOREIGN KEY (flair_id) REFERENCES Flair(id)
              ON DELETE RESTRICT
        )
    """)

    rows = c.execute("SELECT * FROM ri_temp").fetchall()
    extended = [(row["id"], row["created_utc"], None, None, None)
                for row in rows]
    c.executemany("""
        INSERT INTO RedditInfo(id, created_utc, upvotes, flair_id, selftext)
        VALUES (?, ?, ?, ?, ?)
    """, extended)

    c.execute("DROP TABLE ri_temp")

    # to update FK references in other tables
    c.execute("ALTER TABLE RedditInfo RENAME TO ri_temp")
    c.execute("ALTER TABLE ri_temp RENAME TO RedditInfo")

    c.execute("ALTER TABLE AudioFile RENAME TO af_temp")
    c.execute("""
        CREATE TABLE AudioFile(
            id INTEGER PRIMARY KEY ASC,
            collection_id INTEGER,
            date DATE NOT NULL,
            description TEXT,
            filename TEXT NOT NULL,
            title TEXT,
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
        )
    """)

    rows = c.execute("SELECT * FROM af_temp").fetchall()
    extended = [[col for col in row]
                for row in rows]
    if extended:
        c.executemany(f"""
            INSERT INTO AudioFile
            VALUES ({', '.join('?' * len(extended[0]))})
        """, extended)

    c.execute("DROP TABLE af_temp")

    c.execute("CREATE INDEX audio_file_collection_id_idx ON AudioFile(collection_id)")
    c.execute("CREATE INDEX audio_file_alias_id_idx ON AudioFile(alias_id)")

    # to update FK references in other tables
    c.execute("ALTER TABLE AudioFile RENAME TO af_temp")
    c.execute("ALTER TABLE af_temp RENAME TO AudioFile")

    c.execute("ALTER TABLE FileCollection RENAME TO fc_temp")
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
        )
    """)

    rows = c.execute("SELECT * FROM fc_temp").fetchall()
    extended = [[col for col in row]
                for row in rows]
    if extended:
        c.executemany(f"""
            INSERT INTO FileCollection
            VALUES ({', '.join('?' * len(extended[0]))})
        """, extended)

    c.execute("DROP TABLE fc_temp")

    # to update FK references in other tables
    c.execute("ALTER TABLE FileCollection RENAME TO fc_temp")
    c.execute("ALTER TABLE fc_temp RENAME TO FileCollection")

    c.execute("DROP TABLE Titles_fts_idx")

    c.execute("""
        CREATE VIEW v_audio_and_collection_combined
        AS
        SELECT
            AudioFile.id,
            AudioFile.collection_id,
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
            RedditInfo.created_utc as reddit_created_utc,
            RedditInfo.upvotes as reddit_upvotes,
            RedditInfo.selftext as reddit_selftext,
            Flair.name as reddit_flair,
            EXISTS (SELECT 1 FROM ListenLater WHERE audio_id = AudioFile.id) as listen_later
        FROM AudioFile
        LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
        LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
        LEFT JOIN Flair ON RedditInfo.flair_id = Flair.id
        JOIN Alias ON Alias.id = AudioFile.alias_id
        LEFT JOIN Artist ON Artist.id = Alias.artist_id;
    """)

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
        CREATE VIRTUAL TABLE Titles_fts_idx USING fts5(
          audio_title, collection_title,
          content='v_audio_and_collection_titles',
          content_rowid='audio_id');
    """)

    # fill FTS index
    c.execute("""
    INSERT INTO Titles_fts_idx(rowid, audio_title, collection_title)
    SELECT id, title,
        (CASE
         WHEN collection_id IS NULL THEN NULL
         ELSE (SELECT title as collection_title FROM FileCollection WHERE id = collection_id)
         END)
    FROM AudioFile
    """)

    c.execute("""
        CREATE TRIGGER AudioFile_ai AFTER INSERT ON AudioFile
        BEGIN
            INSERT INTO Titles_fts_idx(rowid, audio_title, collection_title)
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
    c.execute("""
        CREATE TRIGGER AudioFile_ad AFTER DELETE ON AudioFile
        BEGIN
            INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, audio_title, collection_title)
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
            INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, audio_title, collection_title)
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
            INSERT INTO Titles_fts_idx(rowid, audio_title, collection_title)
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
