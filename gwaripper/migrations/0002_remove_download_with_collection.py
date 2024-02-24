import sqlite3

date = '2022-08-25'


def upgrade(db_con):
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    c.execute("PRAGMA foreign_keys=off")

    c.execute("ALTER TABLE AudioFile RENAME TO temp")
    c.execute("DROP TABLE Titles_fts_idx")
    c.execute("DROP INDEX audio_file_collection_id_idx")
    c.execute("DROP INDEX audio_file_alias_id_idx")
    c.execute("DROP TRIGGER AudioFile_ai")
    c.execute("DROP TRIGGER AudioFile_ad")
    c.execute("DROP TRIGGER AudioFile_au")
    c.execute("DROP VIEW v_audio_and_collection_combined")
    c.execute("DROP VIEW v_audio_and_collection_titles")
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

    # copy old data
    c.execute(
    """
    INSERT INTO AudioFile
    SELECT
        id, collection_id, date, description, filename, title,
        url, alias_id, rating, favorite
    FROM temp
    """)

    c.execute("""
    -- full text-search virtual table
    -- only stores the idx due to using parameter content='..'
    -- -> external content table (here using a view)
    -- but then we have to keep the content table and the idx up-to-date ourselves
    CREATE VIRTUAL TABLE IF NOT EXISTS Titles_fts_idx USING fts5(
      title, collection_title,
      content='v_audio_and_collection_titles',
      content_rowid='audio_id')
    """)

    # fill FTS index
    c.execute("""
    INSERT INTO Titles_fts_idx(rowid, title, collection_title)
    SELECT id, title,
        (CASE
         WHEN collection_id IS NULL THEN NULL
         ELSE (SELECT title as collection_title FROM FileCollection WHERE id = collection_id)
         END)
    FROM AudioFile
    """)

    # re-create triggers, views and indices after inserting
    c.execute("CREATE INDEX audio_file_collection_id_idx ON AudioFile(collection_id)")
    c.execute("CREATE INDEX audio_file_alias_id_idx ON AudioFile(alias_id)")

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
        RedditInfo.created_utc as reddit_created_utc
    FROM AudioFile
    LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
    LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
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
    LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id;
    """)

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
    END;""")

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
    END;""")

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
        END;
    """)

    c.execute("DROP TABLE temp")
    c.execute("PRAGMA foreign_keys=on")
