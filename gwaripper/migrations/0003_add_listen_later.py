import datetime
import sqlite3

date = '2023-10-15'


def upgrade(db_con):
    rf = db_con.row_factory
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    db_con.row_factory = rf

    c.execute("""
        CREATE TABLE ListenLater (
          id INTEGER PRIMARY KEY ASC,
          audio_id INTEGER,
          FOREIGN KEY (audio_id) REFERENCES AudioFile(id)
            ON DELETE CASCADE
        )""")

    c.execute("DROP VIEW v_audio_and_collection_combined")
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
            EXISTS (SELECT 1 FROM ListenLater WHERE audio_id = AudioFile.id) as listen_later
        FROM AudioFile
        LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
        LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
        JOIN Alias ON Alias.id = AudioFile.alias_id
        LEFT JOIN Artist ON Artist.id = Alias.artist_id
        """)
