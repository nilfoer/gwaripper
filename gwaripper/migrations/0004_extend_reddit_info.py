import sqlite3

date = '2024-07-14'


def upgrade(db_con):
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    c.execute("ALTER TABLE RedditInfo RENAME TO ri_temp")
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
    c.execute("""
        CREATE TABLE Flair(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL
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

    c.execute("DROP VIEW v_audio_and_collection_combined")
    c.execute("ALTER TABLE RedditInfo RENAME TO ri_temp")
    c.execute("ALTER TABLE ri_temp RENAME TO RedditInfo")

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
            Flair.name as reddit_flair,
            EXISTS (SELECT 1 FROM ListenLater WHERE audio_id = AudioFile.id) as listen_later
        FROM AudioFile
        LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
        LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
        LEFT JOIN Flair ON RedditInfo.flair_id = Flair.id
        JOIN Alias ON Alias.id = AudioFile.alias_id
        LEFT JOIN Artist ON Artist.id = Alias.artist_id;
    """)
