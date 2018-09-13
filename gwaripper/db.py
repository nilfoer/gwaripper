import logging
import os
import time
import shutil
import sqlite3
import csv

from .config import config, write_config_module, ROOTDIR

logger = logging.getLogger(__name__)


def load_or_create_sql_db(filename):
    """
    Creates connection to sqlite3 db and a cursor object. Creates the table if it doesnt exist yet since,
    the connect function creates the file if it doesnt exist but it doesnt contain any tables then.

    :param filename: Filename string/path to file
    :return: connection to sqlite3 db and cursor instance
    """
    conn = sqlite3.connect(filename)
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT, "
              "description TEXT, local_filename TEXT, title TEXT, url_file TEXT, url TEXT, created_utc REAL, "
              "r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
              "sgasm_user TEXT, subreddit_name TEXT)")
    # commit changes
    conn.commit()

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
