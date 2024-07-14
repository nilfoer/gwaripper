import logging
import os
import time
import shutil
import sqlite3
import datetime
import csv
import re
import enum

from typing import Tuple, Optional, Set, Dict, Sequence, List

from .config import config, write_config_module
from . import migrate
from .info import DELETED_USR_FOLDER, UNKNOWN_USR_FOLDER
from .exceptions import GWARipperError

logger = logging.getLogger(__name__)


# E. Langloise: PEP 519 recommends using typing.Union[str, bytes, os.PathLike]
# for filenames
# only use str for now
def load_or_create_sql_db(filename: str) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
    """
    Creates connection to sqlite3 db and a cursor object.
    Creates file and tables if it doesn't exist!

    :param filename: Filename string/path to file
    :return: connection to sqlite3 db and cursor instance
    """
    create_new = not os.path.isfile(filename)
    if create_new:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(filename,
                                               detect_types=sqlite3.PARSE_DECLTYPES)

    if create_new:
        # context mangaer auto-commits changes or does rollback on exception
        with conn:
            conn.executescript(f"""
                PRAGMA foreign_keys=off;
                BEGIN IMMEDIATE TRANSACTION;

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
                );

                -- Indexes are implicitly created only in the case of PRIMARY KEY
                -- and UNIQUE statements
                CREATE INDEX audio_file_collection_id_idx ON AudioFile(collection_id);
                CREATE INDEX audio_file_alias_id_idx ON AudioFile(alias_id);

                -- so we can match aliases to an artist and use the artist name for displaying
                -- all the files of it's aliases
                -- files will still be stored under the alias name though since if we don't have
                -- reddit information we can't match an audio host user name (alias) to an artist
                -- without user interaction and we also can't match on similarity
                -- matching later when we have reddit info that links an alias an artist is also
                -- not an option since we'd have to move the files which might not be present
                -- anymore (e.g. backed up somewhere else)
                CREATE TABLE Artist(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );

                CREATE TABLE Alias(
                    id INTEGER PRIMARY KEY ASC,
                    artist_id INTEGER,
                    name TEXT UNIQUE NOT NULL,
                    FOREIGN KEY (artist_id) REFERENCES Artist(id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX alias_artist_id_idx ON Alias(artist_id);

                INSERT OR IGNORE INTO Alias(name) VALUES ('{DELETED_USR_FOLDER}');
                INSERT OR IGNORE INTO Alias(name) VALUES ('{UNKNOWN_USR_FOLDER}');

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
                );

                CREATE TABLE RedditInfo(
                    id INTEGER PRIMARY KEY ASC,
                    created_utc REAL,
                    upvotes INTEGER,
                    flair_id INTEGER,
                    selftext TEXT,
                    FOREIGN KEY (flair_id) REFERENCES Flair(id)
                      ON DELETE RESTRICT
                );

                CREATE TABLE Flair(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );

                CREATE TABLE ListenLater (
                  id INTEGER PRIMARY KEY ASC,
                  audio_id INTEGER,
                  FOREIGN KEY (audio_id) REFERENCES AudioFile(id)
                    ON DELETE CASCADE
                );

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

                CREATE VIEW v_audio_and_collection_titles
                AS
                SELECT
                    AudioFile.id as audio_id,
                    FileCollection.title as collection_title,
                    AudioFile.title as audio_title
                FROM AudioFile
                LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id;

                -- full text-search virtual table
                -- only stores the idx due to using parameter content='..'
                -- -> external content table (here using a view)
                -- but then we have to keep the content table and the idx up-to-date ourselves
                CREATE VIRTUAL TABLE IF NOT EXISTS Titles_fts_idx USING fts5(
                  title, collection_title,
                  content='v_audio_and_collection_titles',
                  content_rowid='audio_id');

                -- in this case also possible using one trigger with case/when since we're
                -- inserting into the same table etc.
                -- WHEN NULL does not work it just appeared to work since the subquery
                -- with WHERE FileCollection.id = NULL returned no rows which means NULL will
                -- be inserted (which we could use but then the subquery would be run every time)
                -- use WHEN new.collection_id IS NULL instead
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
                END;

                -- the values inserted into the other columns must match the values
                -- currently stored in the table otherwise the results may be unpredictable
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
                END;

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

                -- VERSION TABLE
                CREATE TABLE IF NOT EXISTS {migrate.VERSION_TABLE} (
                    version_id INTEGER PRIMARY KEY ASC,
                    dirty INTEGER NOT NULL
                );
                INSERT INTO {migrate.VERSION_TABLE} VALUES ({migrate.LATEST_VERSION}, 0);

                COMMIT;
                PRAGMA foreign_keys=on;
            """)
    else:
        # NOTE: migrate DB; context manager automatically closes connection
        with migrate.Database(filename) as migration:
            migration_success = migration.upgrade_to_latest()
        if not migration_success:
            conn.close()
            raise GWARipperError("Could not migrate DB! Open an issue at "
                                 "github.com/nilfoer/gwaripper")

    # Row provides both index-based and case-insensitive name-based access
    # to columns with almost no memory overhead
    conn.row_factory = sqlite3.Row

    # make sure foreign key support is activated
    # NOTE: even though i was setting PRAGMA foreign_keys=on in the db creation
    # script it still had the foreign_keys turned off somehow
    with conn:
        c = conn.execute("PRAGMA foreign_keys=on")

    return conn, c


def export_table_to_csv(db_con: sqlite3.Connection, filename: str, table_name: str) -> None:
    """
    Fetches and writes all rows (with all cols) in db_con's database to the file filename using
    writerows() from the csv module

    writer kwargs: dialect='excel', delimiter=";"

    :param filename: Filename or path to file
    :param db_con: Connection to sqlite db
    :return: None
    """
    # newline="" <- important otherwise weird behaviour with multiline cells (adding \r) etc.
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        # excel dialect -> which line terminator(\r\n), delimiter(,) to use,
        # when to quote cells etc.
        csvwriter = csv.writer(csvfile, dialect="excel", delimiter=";")

        # get rows from db
        c = db_con.execute(f"SELECT * FROM {table_name}")
        rows = c.fetchall()

        # cursor.description -> sequence of 7-item sequences each containing
        # info describing one result column
        col_names = [description[0] for description in c.description]
        csvwriter.writerow(col_names)  # header
        # write the all the rows to the file
        csvwriter.writerows(rows)


def convert_or_escape_to_str(column_value):
    if column_value is None:
        return 'NULL'
    elif isinstance(column_value, datetime.date):
        # sqlite3 stores dates among others as TEXT as ISO8601 strings
        # return f"'{column_value.strftime('%Y-%m-%d')}'"
        return f"'{column_value.isoformat()}'"
    elif isinstance(column_value, datetime.datetime):
        # return f"'{column_value.strftime('%Y-%m-%dT%H:%M:%S')}'"
        return f"'{column_value.isoformat()}'"
    elif isinstance(column_value, str):
        # escape single quotes using another one
        column_value = column_value.replace("'", "''")
        # enclose in single quotes
        return f"'{column_value}'"
    else:
        return str(column_value)


def export_to_sql(filename, db_con):
    # NOTE: does not support contentless or external content FTS tables
    # NOTE: official iterdump() also breaks when using fts table with
    #       contentless or external content table
    row_fac_bu = db_con.row_factory
    db_con.row_factory = sqlite3.Row

    c = db_con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    sql_master = c.fetchall()

    # store all full text search names here so we can later filter out
    # shadow tables that automatically get created when creating the
    # fts table
    fts_table_names = [r['name'] for r in sql_master
                       if r['sql'] and re.search(r'using fts\d\(', r['sql'], re.IGNORECASE)]

    # sql statement is exactly the same as when table/index/trigger was
    # created, including comments
    index_creation_statements = []
    table_names = []
    trigger_creation_statements = []
    result = ["PRAGMA foreign_keys=off;", "BEGIN TRANSACTION;"]
    for row in sql_master:
        if row['name'].startswith("sqlite_autoindex_"):
            continue
        type_name = row['type']
        if type_name == 'trigger':
            trigger_creation_statements.append((row['name'], row['sql']))
        elif type_name == 'index':
            index_creation_statements.append((row['name'], row['sql']))
        elif type_name == 'table':
            # fts shadow have name of the form: f'{fts_table_name}_{subtable}'
            # where subtable can be data, config, docsize and more
            # NOTE: maybe we omit some configuration by not copying values from _config?
            prefix = row['name'].rsplit('_', 1)[0]
            # compare length so we don't omit the fts table itself
            if any(1 for tbl_name in fts_table_names
                   if len(row['name']) > len(tbl_name) and tbl_name == prefix):
                continue

            # filter shadow tables created automatically by fts tables
            table_names.append(row['name'])
            # create all tables first
            result.append(f"{row['sql']};")
        elif type_name == 'view':
            result.append(f"{row['sql']};")
        else:
            assert 0

    # insert all the values
    for tbl_name in table_names:
        result.append(f"INSERT INTO \"{tbl_name}\" VALUES")
        table_rows = c.execute(f"SELECT * FROM {tbl_name}").fetchall()
        for i, tr in enumerate(table_rows):
            result.append(f"({','.join(convert_or_escape_to_str(c) for c in tr)})"
                          f"{';' if i == len(table_rows)-1 else ','}")

    for idx_name, idx_statement in index_creation_statements:
        result.append(f"{idx_statement};")

    for trigger_name, trigger_statement in trigger_creation_statements:
        result.append(f"{trigger_statement};")

    result.append("COMMIT;")
    result.append("PRAGMA foreign_keys=on;")

    with open(filename, 'w', encoding='UTF-8') as f:
        f.write("\n".join(result))

    db_con.row_factory = row_fac_bu


def db_to_sql_insert_only(db_con: sqlite3.Connection) -> str:
    # NOTE: will not collect insert statements from external content FTS tables
    row_fac_bu = db_con.row_factory
    db_con.row_factory = sqlite3.Row

    c = db_con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name")
    sql_master = c.fetchall()

    fts_tables = [r['name'] for r in sql_master
                  if re.search(r'using fts\d\(', r['sql'], re.IGNORECASE)]

    result: List[str] = ["PRAGMA foreign_keys=off;", "BEGIN TRANSACTION;"]
    # insert all the values
    for r in sql_master:
        tbl_name = r['name']
        # filter out contentless and external content fts tables
        if tbl_name in fts_tables and "content=" in r['sql']:
            continue
        # fts shadow have name of the form: f'{fts_table_name}_{subtable}'
        # where subtable can be data, config, docsize and more
        prefix = tbl_name.rsplit('_', 1)[0]
        # compare length so we don't omit the fts table itself
        if any(1 for fts_name in fts_tables
               if len(r['name']) > len(fts_name) and fts_name == prefix):
            continue

        table_rows = c.execute(f"SELECT * FROM {tbl_name}").fetchall()
        if len(table_rows) > 0:
            result.append(f"INSERT INTO \"{tbl_name}\" VALUES")
        for i, tr in enumerate(table_rows):
            result.append(f"({','.join(convert_or_escape_to_str(c) for c in tr)})"
                          f"{';' if i == len(table_rows)-1 else ','}")

    result.append("COMMIT;")
    result.append("PRAGMA foreign_keys=on;")

    db_con.row_factory = row_fac_bu

    return "\n".join(result)


def backup_db(db_path: str, bu_dir: str,
              csv_path: Optional[str] = None, force_bu: bool = False):
    """
    Backups db_path and csv_path (if not None) to bu_dir if the time since last backup is greater
    than db_bu_freq (in days, also from cfg) or force_bu is True
    Updates last_db_bu time in cfg and deletes oldest backup along with csv (if present) if
    number of sqlite files in backup dir > max_db_bu in cfg

    If next backup isnt due yet announce when next bu will be

    :param db_path: Path to .sqlite db
    :param bu_dir: Path to location of backups
    :param csv_path: Optional, path to csv file thats been exported from sqlite db
    :param force_bu: True -> force backup no matter last_db_bu time
    :return: None
    """
    os.makedirs(bu_dir, exist_ok=True)
    # time.time() get utc number
    now = time.time()
    # freq in days convert to secs since utc time is in secs since epoch
    freq_secs: float = config.getfloat(
        "Settings", "db_bu_freq", fallback=5.0) * 24 * 60 * 60
    elapsed_time: float = now - \
        config.getfloat("Time", "last_db_bu", fallback=0.0)

    # if time since last db bu is greater than frequency in settings or we want to force a bu
    # time.time() is in gmt/utc whereas time.strftime() uses localtime
    if (elapsed_time > freq_secs) or force_bu:
        time_str = time.strftime("%Y-%m-%d")
        logger.info("Writing backup of database to {}".format(bu_dir))
        con = sqlite3.connect(db_path)

        # by confused00 https://codereview.stackexchange.com/questions/78643/create-sqlite-backups
        # Lock database before making a backup
        # After a BEGIN IMMEDIATE, no other database connection will be able to
        # write to the database persists until the next COMMIT or ROLLBACK
        con.execute('begin immediate')
        # Make new backup file
        # shutil.copy2 also copies metadata -> ctime (Unix: time of the last
        # metadata change, Win: creation time for path) doesnt change -> use mtime
        # for sorting (doesnt change but we can assume oldest bu also has oldest
        # mtime) whereas ctime could be the same for all) or use shutil.copy ->
        # only copies permission not m,ctime etc
        shutil.copy(db_path, os.path.join(
            bu_dir, "{}_gwarip_db.sqlite".format(time_str)))
        # Unlock database
        con.rollback()
        con.close()

        if csv_path:
            shutil.copy(csv_path, os.path.join(
                bu_dir, "{}_gwarip_db_exp.csv".format(time_str)))

        # update last db bu time
        if config.has_section("Time"):
            config["Time"]["last_db_bu"] = str(now)
        else:
            config["Time"] = {"last_db_bu": str(now)}
        # write config to file
        write_config_module()

        bu_dir_list = [os.path.join(bu_dir, f) for f in os.listdir(bu_dir)
                       if f.endswith(".sqlite")]

        # if there are more files than number of bu allowed (2 files per bu atm)
        if len(bu_dir_list) > (config.getint("Settings", "max_db_bu", fallback=5)):
            # use creation time (getctime) for sorting, due to how name the
            # files we could also sort alphabetically
            bu_dir_list = sorted(bu_dir_list, key=os.path.getctime)

            oldest = os.path.basename(bu_dir_list[0])
            logger.info(
                "Too many backups, deleting oldest one: {}".format(oldest))

            os.remove(bu_dir_list[0])
            # try to delete csv of same day, since bu of csv is optional
            try:
                os.remove(os.path.join(bu_dir, oldest[:-7] + "_exp.csv"))
            except FileNotFoundError:
                logger.debug("No csv file backup of that day")
            else:
                logger.info(
                    "Also deleted csv backup, that was created on the same day!")
    else:
        # time in sec that is needed to reach next backup
        next_bu = freq_secs - elapsed_time
        logger.info("The last backup date is not yet {} days old! "
                    "The next backup will be in {: .2f} days!".format(
                        config.getfloat(
                            "Settings", "db_bu_freq", fallback=5.0),
                        next_bu / 24 / 60 / 60))


def set_favorite_entry(db_con: sqlite3.Connection, _id: int, fav_intbool: int) -> None:
    with db_con:
        db_con.execute(
            "UPDATE AudioFile SET favorite = ? WHERE id = ?", (fav_intbool, _id))


def set_rating(db_con: sqlite3.Connection, _id: int, rating: float):
    with db_con:
        db_con.execute(
            "UPDATE AudioFile SET rating = ? WHERE id = ?", (rating, _id))


def remove_entry(db_con: sqlite3.Connection, _id: int, root_dir: str):
    c = db_con.execute(
        "SELECT collection_id FROM AudioFile WHERE id = ?", (_id,))
    collection_id_row = c.fetchone()

    with db_con:
        c.execute("DELETE FROM AudioFile WHERE id = ?", (_id,))

        # NOTE: should we try to del collection and except if it still has children
        # due to FOREIGN KEY ON DELETE RESTRICT
        # or should we check for children and delete if there are none?
        # -> do the former for now
        if collection_id_row is not None:
            collection_id = collection_id_row[0]
            try:
                c.execute("DELETE FROM FileCollection WHERE id = ?",
                          (collection_id,))
            except sqlite3.IntegrityError:
                # raises IntegrityError when we try to delete a FileCollection
                # that still has an AudioFile
                pass


# helper class to turn attribute-based acces into dict-like acces on sqlite3.Row
class RowData:
    def __init__(self, row: sqlite3.Row):
        self.row = row

    def __getattr__(self, attr):
        return self.row[attr]


def get_x_entries(con: sqlite3.Connection, x: int,
                  after: Optional[int] = None, before: Optional[int] = None,
                  order_by: str = "AudioFile.id DESC"):
    # order by has to come b4 limit/offset
    # alias the view v_.. as AudioFile so we can use regular order_by
    # with the actual table name
    query = f"""
            SELECT * FROM v_audio_and_collection_combined AudioFile
            ORDER BY {order_by}
            LIMIT ?"""
    query, vals_in_order = keyset_pagination_statment(
        query, [], after=after, before=before,
        order_by=order_by, first_cond=True)
    c = con.execute(query, (*vals_in_order, x))
    rows = c.fetchall()

    if rows:
        return [RowData(row) for row in rows]
    else:
        return None


def get_x_listen_later_entries(con: sqlite3.Connection, x: int,
                               after: Optional[int] = None, before: Optional[int] = None,
                               order_by: str = "AudioFile.id DESC"):
    # order by has to come b4 limit/offset
    # alias the view v_.. as AudioFile so we can use regular order_by
    # with the actual table name
    query = f"""
        SELECT AudioFile.* FROM ListenLater
        LEFT JOIN v_audio_and_collection_combined AS AudioFile ON AudioFile.id = ListenLater.audio_id
        ORDER BY {order_by}
        LIMIT ?"""
    query, vals_in_order = keyset_pagination_statment(
        query, [], after=after, before=before,
        order_by=order_by, first_cond=True)
    c = con.execute(query, (*vals_in_order, x))
    rows = c.fetchall()

    if rows:
        return [RowData(row) for row in rows]
    else:
        return None


VALID_ORDER_BY = {"ASC", "DESC", "AudioFile.id",
                  "AudioFile.rating", "id", "rating"}


def validate_order_by_str(order_by):
    for part in order_by.split(" "):
        if part not in VALID_ORDER_BY:
            return False
    return True


# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (optionally
# followed by some whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


VALID_SEARCH_COLS: Set[str] = {
    "title", "rating", "favorite", "artist", "url", "reddit_id"
}


# searching AudioFile and FileCollection tables directly and just retrieving
# the ids and then getting the fully joined result from the view
# is just as fast querying against the view directly since the query gets
# flattened (just make sure that it does!)
# only true since we need the join anyway populating an object for the collection
# once and then storing that reference for the children would speed it up
#
# search in view
# SELECT * FROM v_audio_and_collection_combined WHERE alias_id = 3 OR url = '...'
# vs. search in tables directly
# SELECT * FROM v_audio_and_collection_combined WHERE id IN (
#   SELECT id FROM AudioFile WHERE alias_id = 3 OR url = '...'
# )
# also tested:
# SELECT * FROM v_audio_and_collection_combined WHERE fcol_url = '...'
# vs.
# below also tested with inner join instead of subquery
# SELECT * FROM v_audio_and_collection_combined WHERE id IN (
#   SELECT id FROM AudioFile WHERE collection_id = (SELECT FileCollection.id FROM FileCollection
#                                                   WHERE url = '...')
# )

# NOTE: WARNING enum members all evaluate to True
# so explicitly test "op != ConditionalOp.NONE" instead of "if not op"
class ConditionalOp(enum.Enum):
    # guaranteed to need no conditional op but others might not need one
    NONE = 0
    OR = 1
    AND = 2


# these should later probably emit the search expression string themselves
class SearchColumnExpression:
    __slots__ = ('conditional_op', 'column_name', 'search_value')

    def __init__(self, conditional_op: ConditionalOp,
                 column_name: str, search_value: Optional[str] = None):
        self.conditional_op = conditional_op
        self.column_name = column_name
        self.search_value = search_value


class SearchExpression:
    __slots__ = ('conditional_op', 'column_expressions')

    def __init__(self, conditional_op: ConditionalOp,
                 column_expressions: List[SearchColumnExpression]):
        self.conditional_op = conditional_op
        self.column_expressions = column_expressions


# for turning a search keyword into multiple columns or an actual column name
# now including conditional operator
SEARCH_COL_TRANSFORM: Dict[str, SearchExpression] = {
    "artist": SearchExpression(ConditionalOp.AND, [
        SearchColumnExpression(ConditionalOp.NONE, "artist_name"),
        SearchColumnExpression(ConditionalOp.OR, "alias_name"),
        SearchColumnExpression(ConditionalOp.OR, "fcol_alias_name")]),
    "url": SearchExpression(ConditionalOp.AND, [
        SearchColumnExpression(ConditionalOp.NONE, "url"),
        SearchColumnExpression(ConditionalOp.OR, "fcol_url")]),
    "reddit_id": SearchExpression(ConditionalOp.AND,
                                  [SearchColumnExpression(ConditionalOp.NONE, "fcol_id_on_page")])
}


def search_sytnax_parser(search_str: str,
                         delimiter: str = ";",
                         **kwargs) -> Tuple[List[SearchExpression], str]:
    search_expressions: List[SearchExpression] = []
    # Return all non-overlapping matches of pattern in string, as a list of strings.
    # The string is scanned left-to-right, and matches are returned in the order found.
    # If one or more groups are present in the pattern, return a list of groups; this will
    # be a list of tuples if the pattern has more than one group. Empty matches are included
    # in the result.
    search_col = None
    title_search: List[str] = []
    for match in WORD_RE.findall(search_str):
        single, multi_word = match
        part = None
        # single alwys has : included unless its not our syntax
        # since col:akdka;dajkda;dakda is one single word and col: is too
        if single:
            if ":" in single:
                # -> search type is part of the word
                search_col, part = single.split(":", 1)
                if search_col not in VALID_SEARCH_COLS:
                    logger.info(
                        "'%s' is not a supported search type!", search_col)
                    # set to None so we skip adding search_options for next word (which
                    # still belongs to unsupported search_col)
                    search_col = None
                    continue
                if not part:
                    # if part empty it was col:"multi-word"
                    continue
            else:
                # multiple single words after each other -> use to search for title
                # with normal syntax col is always in single word and no col if
                # search_col isnt set so we can append all single words till we find a single
                # word with :
                title_search.append(single)
                continue

        # search_col is None if search_col isnt supported
        # then we want to ignore this part of the search
        if search_col is None:
            continue

        # a or b -> uses whatever var is true -> both true (which cant happen here) uses
        # first one
        part = part or multi_word

        if search_col in SEARCH_COL_TRANSFORM:
            search_expr = SEARCH_COL_TRANSFORM[search_col]
            for column_expr in search_expr.column_expressions:
                column_expr.search_value = part
            search_expressions.append(search_expr)
        else:
            search_expressions.append(
                # assume AND
                SearchExpression(ConditionalOp.AND, [
                    SearchColumnExpression(ConditionalOp.NONE, search_col, part)])
            )

    return search_expressions, " ".join(title_search)


def search(db_con, query, order_by="AudioFile.id DESC", **kwargs):
    # validate order_by from user input
    if not validate_order_by_str(order_by):
        logger.warning("Sorting %s is not supported", order_by)
        order_by = "AudioFile.id DESC"

    search_expressions, title_search_str = search_sytnax_parser(
        query, **kwargs)

    if search_expressions or title_search_str:
        rows = search_normal_columns(
            db_con, search_expressions, title_search_str,
            order_by=order_by, **kwargs)
        if rows is None:
            return None
        else:
            return [RowData(row) for row in rows]
    else:
        return get_x_entries(kwargs.pop("limit", 60), order_by=order_by, **kwargs)


def search_normal_columns(
        db_con: sqlite3.Connection, search_expressions: List[SearchExpression],
        title_search_str: str, additional_conditions="",
        order_by="AudioFile.id DESC", limit=-1,  # no row limit when limit is neg. nr
        after=None, before=None):
    """Can search in normal columns as well as multiple associated columns
    (connected via bridge table) and both include and exclude them"""
    # @Cleanup mb split into multiple funcs that just return the conditional string
    # like: WHERE title LIKE ? and the value, from_table_names etc.?

    # conditionals
    cond_statements: List[str] = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order = []
    # build conditionals for select string

    if title_search_str:
        # wrap search str in double quotes so "-" can be used inside it
        title_search_str = " ".join(f'"{word}"' if "-" in word else word
                                    for word in title_search_str.split(" "))
        # use full-text-search for titles
        cond_statements.append(
            f"{'AND' if cond_statements else 'WHERE'} AudioFile.id IN "
            "(SELECT rowid FROM Titles_fts_idx WHERE Titles_fts_idx MATCH ?)")
        vals_in_order.append(title_search_str)

    for search_expr in search_expressions:
        sub_expression = []
        for search_column_expr in search_expr.column_expressions:
            if not search_column_expr.search_value:
                continue
            # NOTE: enum members all evaluate to True
            cond_op = search_column_expr.conditional_op
            if cond_op != ConditionalOp.NONE:
                sub_expression.append('AND' if cond_op ==
                                      ConditionalOp.AND else 'OR')
            sub_expression.append(
                f"AudioFile.{search_column_expr.column_name} = ?")
            vals_in_order.append(search_column_expr.search_value)

        cond_statements.append(
            f"{'AND' if cond_statements else 'WHERE'} ({' '.join(sub_expression)})")

    if additional_conditions:
        cond_statements.append(
            f"{'AND' if cond_statements else 'WHERE'} ({additional_conditions})")
    cond_statements_str = "\n".join(cond_statements)

    # NOTE: alias view as AudioFile so we can keep other parts of this function
    # unchanged
    query = f"""
            SELECT AudioFile.*
            FROM v_audio_and_collection_combined AudioFile
            {cond_statements_str}
            ORDER BY {order_by}
            LIMIT ?"""
    # important to do this last and limit mustnt be in vals_in_order (since its after
    # keyset param in sql substitution)
    query, vals_in_order = keyset_pagination_statment(
        query, vals_in_order, after=after, before=before,
        order_by=order_by, first_cond=not bool(cond_statements)
    )
    try:
        c = db_con.execute(query, (*vals_in_order, limit))
    except sqlite3.OperationalError as e:
        # str(exception) gives exception msg string
        # while repr(exception) gives exception type and msg
        # only allowed special chars in fts string are:
        # asterisk*, parentheses() and plus+
        # dash- gets parsed as part of a column filter although you normally
        # separate the col filter with a colon: from the rest of the query
        # means not to look at the col
        # https://www.sqlite.org/fts5.html#fts5_column_filters allows more special chars
        # double-quotes" would normally be allowed but due to the way search_sytnax_parser
        # does the parsing they're not with our implementation
        if "fts5: syntax error" in str(e):
            return None
        else:
            raise

    rows = c.fetchall()

    return rows


def insert_order_by_id(query, order_by="AudioFile.id DESC"):
    # !! Assumes SQL statements are written in UPPER CASE !!
    # also sort by id secondly so order by is unique (unless were already using id)
    if "audiofile.id" not in order_by.lower():
        query = query.splitlines()
        # if we have subqueries take last order by to insert; strip line of whitespace since
        # we might have indentation
        order_by_i = [i for i, ln in enumerate(
            query) if ln.strip().startswith("ORDER BY")][-1]
        inserted = f"ORDER BY {order_by}, {order_by.split('.')[0]}.id {order_by.split(' ')[1]}"
        query[order_by_i] = inserted
        query = "\n".join(query)
    return query


def keyset_pagination_statment(query, vals_in_order, after=None, before=None,
                               order_by="AudioFile.id DESC", first_cond=False):
    """Finalizes query by inserting keyset pagination statement
    Must be added/called last!
    !! Assumes SQL statements are written in UPPER CASE !!
    :param query: Query string
    :param vals_in_order: List of values that come before id after/before in terms of parameter
                          substitution; Might be None if caller wants to handle it himself
    :param order_by: primary column to sort by and the sorting order e.g. Books.id DESC
    :param first_cond: If the clause were inserting will be the first condition in the statment
    :return: Returns finalized query and vals_in_order"""
    # CAREFUL order_by needs to be unique for keyset pagination, possible to add rnd cols
    # to make it unique
    if after is not None and before is not None:
        raise ValueError(
            "Either after or before can be supplied but not both!")
    elif after is None and before is None:
        return insert_order_by_id(query, order_by), vals_in_order

    result = None
    asc = True if order_by.lower().endswith("asc") else False
    if after is not None:
        comp = ">" if asc else "<"
    else:
        comp = "<" if asc else ">"

    # @Cleanup assuming upper case sqlite statements
    lines = [l.strip() for l in query.splitlines()]
    insert_before = [i for i, l in enumerate(lines) if l.startswith("GROUP BY") or
                     l.startswith("ORDER BY")][0]
    un_unique_sort_col = "audiofile.id" not in order_by.lower()
    if un_unique_sort_col:
        order_by_col = order_by.split(' ')[0]
        # 2-tuple of (primary, secondary)
        primary, secondary = after if after is not None else before
        # if primary is NULL we need IS NULL as "equals comparison operator" since
        # normal comparisons with NULL are always False
        if primary is None:
            equal_comp = "IS NULL"
        else:
            equal_comp = "== ?"
        # for ASCENDING order:
        # slqite sorts NULLS first by default -> when e.g. going forwards in ASC order
        # and we have a NULL value for primary sorting col as last row/book on page
        # we need to include IS NOT NULL condition so we include rows with not-null values
        # if the NULL isnt the last row/book we can go forward normallly
        # if we go backwards we always need to include OR IS NULL since there might be a
        # NULL on the next page
        # if the NULL is first on the page then we need IS NULL and compare the id
        # other way around for DESC order
        # also other way around if sqlite sorted NULLs last (we could also emulate that with
        # ORDER BY (CASE WHEN null_column IS NULL THEN 1 ELSE 0 END) ASC, primary ASC, id ASC)

        # longer but more explicit if clauses
        # if before is not None:
        #     if asc:
        #         # include NULLs when going backwards unless we already had a NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        #     else:
        #         # include NOT NULLs when going backwards unless we already had a
        #         # NOT NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""
        # else:
        #     if asc:
        #         # include NULLs when going forwards unless we already had a NOT NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""
        #     else:
        #         # include NULLs when going forwards unless we already had a NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        if (before is not None and asc) or (after is not None and not asc):
            # ASC: include NULLs when going backwards unless we already had a NULL on the page
            # DESC: include NULLs when going forwards unless we already had a NULL on the page
            null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        elif (before is not None and not asc) or (after is not None and asc):
            # ASC: include NULLs when going forwards unless we already had a NOT NULL on the page
            # DESC: include NOT NULLs when going backwards unless we already had a
            #       NOT NULL on the page
            null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""

        # since we sort by both the primary order by and the id to make the sort unique
        # we need to check for rows matching the value of the sort col -> then we use the id to
        # have a correct sort
        # parentheses around the whole statement important otherwise rows fullfilling the OR
        # statement will get included when searching even if they dont fullfill the rest
        keyset_pagination = (f"{'WHERE' if first_cond else 'AND'} ({order_by_col} {comp} ? "
                             f"OR ({order_by_col} {equal_comp} AND AudioFile.id {comp} ?) "
                             f"{null_clause})")
        # we only need primare 2 times if we compare by a value with ==
        vals_in_order.extend((primary, primary, secondary) if equal_comp.startswith("==")
                             else (primary, secondary))
    else:
        keyset_pagination = f"{'WHERE' if first_cond else 'AND'} AudioFile.id {comp} ?"
        # if vals_in_order is not None:
        vals_in_order.append(after[0] if after is not None else before[0])
    lines.insert(insert_before, keyset_pagination)
    result = "\n".join(lines)
    if un_unique_sort_col:
        result = insert_order_by_id(result, order_by)

    if before is not None:
        # @Cleanup assuming upper case order statment
        # need to reverse order in query to not get results starting from first one possible
        # to before(id) but rather to get limit nr of results starting from before(id)
        result = result.replace(
            f"{' ASC' if asc else ' DESC'}", f"{' DESC' if asc else ' ASC'}")
        result = f"""
            SELECT *
            FROM (
                {result}
            ) AS t
            ORDER BY {order_by.replace('AudioFile.', 't.')}"""
        if un_unique_sort_col:
            # since were using a subquery we need to modify our order by to use the AS tablename
            result = insert_order_by_id(
                result, order_by.replace("AudioFile.", "t."))

    return result, vals_in_order
