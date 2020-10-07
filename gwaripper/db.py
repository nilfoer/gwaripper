import logging
import os
import time
import shutil
import sqlite3
import csv
import re
import operator

from functools import reduce

from .config import config, write_config_module, ROOTDIR

logger = logging.getLogger(__name__)


def load_or_create_sql_db(filename):
    """
    Creates connection to sqlite3 db and a cursor object.
    Creates file and tables if it doesn't exist!

    :param filename: Filename string/path to file
    :return: connection to sqlite3 db and cursor instance
    """
    conn = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)

    # context mangaer auto-commits changes or does rollback on exception
    with conn:
        c = conn.executescript("""
            PRAGMA foreign_keys=off;

            CREATE TABLE IF NOT EXISTS Downloads(
                id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT,
                description TEXT, local_filename TEXT, title TEXT,
                url_file TEXT, url TEXT, created_utc REAL,
                r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,
                reddit_url TEXT, reddit_user TEXT,
                sgasm_user TEXT, subreddit_name TEXT, rating REAL,
                favorite INTEGER);

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
            CREATE TRIGGER IF NOT EXISTS Downloads_ai AFTER INSERT ON Downloads BEGIN
              INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
              VALUES (new.id, new.title, new.reddit_title);
            END;
            CREATE TRIGGER IF NOT EXISTS Downloads_ad AFTER DELETE ON Downloads BEGIN
              INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
              VALUES('delete', old.id, old.title, old.reddit_title);
            END;
            CREATE TRIGGER IF NOT EXISTS Downloads_au AFTER UPDATE ON Downloads BEGIN
              INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
              VALUES('delete', old.id, old.title, old.reddit_title);
              INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
              VALUES (new.id, new.title, new.reddit_title);
            END;

            PRAGMA foreign_keys=on;
        """)

    # Row provides both index-based and case-insensitive name-based access
    # to columns with almost no memory overhead
    conn.row_factory = sqlite3.Row

    return conn, c


def export_csv_from_sql(filename, db_con):
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
        # excel dialect -> which line terminator(\r\n), delimiter(,) to use, when to quote cells etc.
        csvwriter = csv.writer(csvfile, dialect="excel", delimiter=";")

        # get rows from db
        c = db_con.execute("SELECT * FROM Downloads")
        rows = c.fetchall()

        # cursor.description -> sequence of 7-item sequences each containing info describing one result column
        col_names = [description[0] for description in c.description]
        csvwriter.writerow(col_names)  # header
        # write the all the rows to the file
        csvwriter.writerows(rows)


# cant use ROOTDIR in default of bu_dir since it is evaluated at module-level and ROOTDIR might still be None
def backup_db(db_path, csv_path=None, force_bu=False, bu_dir=None):
    """
    Backups db_path and csv_path (if not None) to bu_dir if the time since last backup is greater
    than db_bu_freq (in days, also from cfg) or force_bu is True
    Updates last_db_bu time in cfg and deletes oldest backup along with csv (if present) if
    number of sqlite files in backup dir > max_db_bu in cfg

    If next backup isnt due yet announce when next bu will be

    :param db_path: Path to .sqlite db
    :param csv_path: Optional, path to csv file thats been exported from sqlite db
    :param force_bu: True -> force backup no matter last_db_bu time
    :param bu_dir: Path to location of backup uses ROOTDIR/_db-autobu if None (default: None)
    :return: None
    """
    if bu_dir is None:
        # could also use dir of db_path instead of ROOTDIR
        bu_dir = os.path.join(ROOTDIR, "_db-autobu")
    os.makedirs(bu_dir, exist_ok=True)
    # time.time() get utc number
    now = time.time()
    # freq in days convert to secs since utc time is in secs since epoch
    freq_secs = config.getfloat("Settings", "db_bu_freq", fallback=5.0) * 24 * 60 * 60
    elapsed_time = now - config.getfloat("Time", "last_db_bu", fallback=0.0)

    # if time since last db bu is greater than frequency in settings or we want to force a bu
    # time.time() is in gmt/utc whereas time.strftime() uses localtime
    if (elapsed_time > freq_secs) or force_bu:
        time_str = time.strftime("%Y-%m-%d")
        logger.info("Writing backup of database to {}".format(bu_dir))
        con = sqlite3.connect(db_path)

        # by confused00 https://codereview.stackexchange.com/questions/78643/create-sqlite-backups
        # Lock database before making a backup
        # After a BEGIN IMMEDIATE, no other database connection will be able to write to the database
        # persists until the next COMMIT or ROLLBACK
        con.execute('begin immediate')
        # Make new backup file
        # shutil.copy2 also copies metadata -> ctime (Unix: time of the last metadata change, Win: creation time
        # for path) doesnt change -> use mtime for sorting (doesnt change but we can assume oldest bu also has oldest
        # mtime) whereas ctime could be the same for all) or use shutil.copy -> only copies permission not m,ctime etc
        shutil.copy(db_path, os.path.join(bu_dir, "{}_gwarip_db.sqlite".format(time_str)))
        # Unlock database
        con.rollback()
        con.close()

        if csv_path:
            shutil.copy(csv_path, os.path.join(bu_dir, "{}_gwarip_db_exp.csv".format(time_str)))

        # update last db bu time
        if config.has_section("Time"):
            config["Time"]["last_db_bu"] = str(now)
        else:
            config["Time"] = {"last_db_bu": str(now)}
        # write config to file
        write_config_module()

        # TOCONSIDER Assumption even if f ends with .sqlite it might stil be a dir
        # -> we could check for if..and os.path.isfile(os.path.join(bu_dir, f))
        # iterate over listdir, add file to list if isfile returns true
        bu_dir_list = [os.path.join(bu_dir, f) for f in os.listdir(bu_dir) if f.endswith(".sqlite")]
        # we could also use list(filter(os.path.isfile, bu_dir_list)) but then we need to have a list with PATHS
        # but we need the paths for os.path.getctime anyway
        # filter returns iterator!! that yields items which function is true -> only files
        # iterator -> have to iterate over it or pass it to function that does that -> list() creates a list from it
        # filter prob slower than list comprehension WHEN you call other function (def, lambda, os.path.isfile),
        # WHEREAS you would use a simple if x == "bla" in the list comprehension, here prob same speed

        # if there are more files than number of bu allowed (2 files per bu atm)
        if len(bu_dir_list) > (config.getint("Settings", "max_db_bu", fallback=5)):
            # use creation time (getctime) for sorting, due to how name the files we could also sort alphabetically
            bu_dir_list = sorted(bu_dir_list, key=os.path.getctime)

            oldest = os.path.basename(bu_dir_list[0])
            logger.info("Too many backups, deleting oldest one: {}".format(oldest))
            # TOCONSIDER Robustness check if file is really the one (sqlite) we want to delete first?
            # TOCONSIDER keep deleting till nr of bu == max_db_bu? only relevant if user copied files in there
            os.remove(bu_dir_list[0])
            # try to delete csv of same day, since bu of csv is optional
            try:
                os.remove(os.path.join(bu_dir, oldest[:-7] + "_exp.csv"))
            except FileNotFoundError:
                logger.debug("No csv file backup of that day")
            # if the try clause does not raise an exception
            else:
                logger.info("Also deleted csv backup, that was created on the same day!")
    else:
        # time in sec that is needed to reach next backup
        next_bu = freq_secs - elapsed_time
        logger.info("Der letzte Sicherungszeitpunkt liegt nocht nicht {} Tage zurück! Die nächste Sicherung ist "
                    "in {: .2f} Tagen!".format(config.getfloat("Settings", "db_bu_freq",
                                                               fallback=5), next_bu / 24 / 60 / 60))


def check_direct_url_for_dl(db_con, direct_url):
    """
    Fetches url_file col from db and unpacks the 1-tuples, then checks if direct_url
    is in the list, if found return True

    :param db_con: Connection to sqlite db
    :param direct_url: String of direct url to file
    :return: True if direct_url is in col url_file of db else False
    """
    c = db_con.execute("SELECT url_file FROM Downloads")
    # converting to set would take just as long (for ~10k entries) as searching for it in list
    # returned as list of 1-tuples, use generator to unpack, so when we find direct_url b4
    # the last row we dont have to generate the remaining tuples and we only use it once
    # only minimally faster (~2ms for 10k rows)
    file_urls = (tup[0] for tup in c.fetchall())
    if direct_url in file_urls:
        return True
    else:
        return False


def set_favorite_entry(db_con, _id, fav_intbool):
    with db_con:
        db_con.execute("UPDATE Downloads SET favorite = ? WHERE id = ?", (fav_intbool, _id))


def set_rating(db_con, _id, rating):
    with db_con:
        db_con.execute("UPDATE Downloads SET rating = ? WHERE id = ?", (rating, _id))


def remove_entry(db_con, _id, root_dir):
    c = db_con.execute("SELECT * FROM Downloads WHERE id = ?", (_id,))
    row = RowData(c.fetchone())
    local_filename = row.local_filename
    if not local_filename:
        logger.error("Couldn't remove entry due to a missing local_filename entry! Title: %s",
                     row.title)
        return False
    try:
        os.remove(os.path.join(root_dir, row.sgasm_user, local_filename))
    except FileNotFoundError:
        logger.warning("Didn't find audio file: %s",
                       os.path.join(root_dir, row.sgasm_user, local_filename))
    try:
        os.remove(os.path.join(root_dir, row.sgasm_user, local_filename + ".txt"))
    except FileNotFoundError:
        logger.warning("Didn't find selftext file: %s",
                       os.path.join(root_dir, row.sgasm_user, local_filename + ".txt"))

    with db_con:
        c.execute("DELETE FROM Downloads WHERE id = ?", (_id,))

    return True


# helper class to turn attribute-based acces into dict-like acces on sqlite3.Row
class RowData:
    def __init__(self, row):
        self.row = row

    def __getattr__(self, attr):
        return self.row[attr]


def get_x_entries(con, x, after=None, before=None, order_by="Downloads.id DESC"):
        # order by has to come b4 limit/offset
        query = f"""
                SELECT * FROM Downloads
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


def search_assoc_col_string_parse(valuestring, delimiter=";"):
    """Splits multiple keywords into include kws and exclude kws"""
    # is list comprehension faster even though we have to iterate over the list twice?
    vals_and = []
    vals_ex = []
    # sort vals for search_tags_intersection_exclude func
    for val in valuestring.split(delimiter):
        if val[0] == "!":
            # remove ! then append
            vals_ex.append(val[1:])
        else:
            vals_and.append(val)

    return vals_and, vals_ex


VALID_ORDER_BY = {"ASC", "DESC", "Downloads.id", "Downloads.rating", "id", "rating"}


def validate_order_by_str(order_by):
    for part in order_by.split(" "):
        if part not in VALID_ORDER_BY:
            return False
    return True


# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (followed by some
# whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


VALID_SEARCH_COLS = {"title", "rating", "sgasm_user", "reddit_user", "reddit_url"
                     "r_post_url", "reddit_id", "url"}
ASSOCIATED_COLUMNS = {}


def search_sytnax_parser(search_str,
                         delimiter=";",
                         **kwargs):
    normal_col_values = {}
    assoc_col_values_incl = {}
    assoc_col_values_excl = {}
    # Return all non-overlapping matches of pattern in string, as a list of strings.
    # The string is scanned left-to-right, and matches are returned in the order found.
    # If one or more groups are present in the pattern, return a list of groups; this will
    # be a list of tuples if the pattern has more than one group. Empty matches are included
    # in the result.
    search_col = None
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
                    logger.info("'%s' is not a supported search type!", search_col)
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
                try:
                    normal_col_values["title"] = f"{normal_col_values['title']} {single}"
                except KeyError:
                    normal_col_values["title"] = single
                continue

        # search_col is None if search_col isnt supported
        # then we want to ignore this part of the search
        if search_col is None:
            continue

        # a or b -> uses whatever var is true -> both true (which cant happen here) uses
        # first one
        part = part or multi_word

        if search_col in ASSOCIATED_COLUMNS:
            incl, excl = search_assoc_col_string_parse(part, delimiter=delimiter)
            # make sure not to add an empty list otherwise we wont get an empty dic
            # that evaluates to false for testing in search_normal_mult_assoc
            if incl:
                assoc_col_values_incl[search_col] = incl
            if excl:
                assoc_col_values_excl[search_col] = excl
        else:
            normal_col_values[search_col] = part

    return normal_col_values, assoc_col_values_incl, assoc_col_values_excl


def search(db_con, query, order_by="Downloads.id DESC", **kwargs):
    # validate order_by from user input
    if not validate_order_by_str(order_by):
        logger.warning("Sorting %s is not supported", order_by)
        order_by = "Downloads.id DESC"

    normal_col_values, assoc_col_values_incl, assoc_col_values_excl = search_sytnax_parser(query, **kwargs)

    if normal_col_values or assoc_col_values_incl or assoc_col_values_excl:
        rows = search_normal_mult_assoc(
                db_con, normal_col_values,
                assoc_col_values_incl, assoc_col_values_excl,
                order_by=order_by, **kwargs)
        if rows is None:
            return None
        else:
            return [RowData(row) for row in rows]
    else:
        return get_x_entries(kwargs.pop("limit", 60), order_by=order_by, **kwargs)


def joined_col_name_to_query_names(col_name):
    # TODO mb to Book cls and validate col name
    # have to be careful not to use user input e.g. col_name in SQL query
    # without passing them as params to execute etc.
    table_name = col_name.capitalize()
    bridge_col_name = f"{col_name}_id"
    return table_name, bridge_col_name


def prod(iterable):
    return reduce(operator.mul, iterable, 1)


def search_normal_mult_assoc(
        db_con, normal_col_values, int_col_values_dict, ex_col_values_dict,
        order_by="Downloads.id DESC", limit=-1,  # no row limit when limit is neg. nr
        after=None, before=None):
    """Can search in normal columns as well as multiple associated columns
    (connected via bridge table) and both include and exclude them"""
    # @Cleanup mb split into multiple funcs that just return the conditional string
    # like: WHERE title LIKE ? and the value, from_table_names etc.?

    if int_col_values_dict:
        # nr of items in values multiplied is nr of rows returned needed to match
        # all conditions !! only include intersection vals
        mul_values = prod((len(vals) for vals in int_col_values_dict.values()))
        assoc_incl_cond = f"GROUP BY Downloads.id HAVING COUNT(Downloads.id) = {mul_values}"
    else:
        assoc_incl_cond = ""

    # containing table names for FROM .. stmt
    table_bridge_names = []
    # conditionals
    cond_statements = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order = []
    # build conditionals for select string
    for col, vals in int_col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        table_bridge_names.append(table_name)
        table_bridge_names.append(f"Download{table_name}")

        cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} "
                               f"Downloads.id = Download{table_name}.download_id")
        cond_statements.append(f"AND {table_name}.id = Download{table_name}.{bridge_col_name}")
        cond_statements.append(f"AND {table_name}.name IN ({','.join(['?']*len(vals))})")
        vals_in_order.extend(vals)
    for col, vals in ex_col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        cond_statements.append(f"""
                 {'AND' if cond_statements else 'WHERE'} Downloads.id NOT IN (
                          SELECT Downloads.id
                          FROM Download{table_name} bx, Downloads, {table_name}
                          WHERE Downloads.id = bx.download_id
                          AND bx.{bridge_col_name} = {table_name}.id
                          AND {table_name}.name IN ({', '.join(['?']*len(vals))})
                )""")
        vals_in_order.extend(vals)

    # normal col conditions
    for col, val in normal_col_values.items():
        # use full-text-search for titles
        if "title" in col:
            cond_statements.append(
                    f"{'AND' if cond_statements else 'WHERE'} Downloads.id IN "
                     "(SELECT rowid FROM Downloads_fts_idx WHERE Downloads_fts_idx MATCH ?)")
            vals_in_order.append(val)
        else:
            cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} Downloads.{col} = ?")
            vals_in_order.append(val)

    table_bridge_names = ", ".join(table_bridge_names)
    cond_statements = "\n".join(cond_statements)

    query = f"""
            SELECT Downloads.*
            FROM Downloads{',' if table_bridge_names else ''} {table_bridge_names}
            {cond_statements}
            {assoc_incl_cond}
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


def insert_order_by_id(query, order_by="Downloads.id DESC"):
    # !! Assumes SQL statements are written in UPPER CASE !!
    # also sort by id secondly so order by is unique (unless were already using id)
    if "downloads.id" not in order_by.lower():
        query = query.splitlines()
        # if we have subqueries take last order by to insert; strip line of whitespace since
        # we might have indentation
        order_by_i = [i for i, ln in enumerate(query) if ln.strip().startswith("ORDER BY")][-1]
        inserted = f"ORDER BY {order_by}, {order_by.split('.')[0]}.id {order_by.split(' ')[1]}"
        query[order_by_i] = inserted
        query = "\n".join(query)
    return query


def keyset_pagination_statment(query, vals_in_order, after=None, before=None,
                               order_by="Downloads.id DESC", first_cond=False):
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
        raise ValueError("Either after or before can be supplied but not both!")
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
    un_unique_sort_col = "downloads.id" not in order_by.lower()
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
                             f"OR ({order_by_col} {equal_comp} AND Downloads.id {comp} ?) "
                             f"{null_clause})")
        # we only need primare 2 times if we compare by a value with ==
        vals_in_order.extend((primary, primary, secondary) if equal_comp.startswith("==")
                             else (primary, secondary))
    else:
        keyset_pagination = f"{'WHERE' if first_cond else 'AND'} Downloads.id {comp} ?"
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
        result = result.replace(f"{' ASC' if asc else ' DESC'}", f"{' DESC' if asc else ' ASC'}")
        result = f"""
            SELECT *
            FROM (
                {result}
            ) AS t
            ORDER BY {order_by.replace('Downloads.', 't.')}"""
        if un_unique_sort_col:
            # since were using a subquery we need to modify our order by to use the AS tablename
            result = insert_order_by_id(result, order_by.replace("Downloads.", "t."))

    return result, vals_in_order
