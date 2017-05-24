import sqlite3
import pandas as pd
import os

r_path = os.getcwd()

df = pd.read_csv(os.path.join(r_path, "sgasm_rip_db.csv"), sep=";", encoding="utf-8", index_col=0)

conn = sqlite3.connect(os.path.join(r_path, "gwarip_db.sqlite"))

# with automatically commits the connection and does a rollback in case of an exception BUT DOESNT CLOSE IT!!!!
# with conn:
df.to_sql("Downloads", conn)

with conn:
    cur = conn.cursor()
    # create id col as PRIMARY KEY that increases automatically, reoder and rename cols
    # synatx:
    # INSERT INTO table1 ( column1 )
    # SELECT  col1
    # FROM    table2
    # !!!!!!!!! executescript calls COMMIT FIRST and THEN executes the script !!!!!!!!!!!!!!
    cur.executescript("""
    CREATE TABLE my_table_copy(
    id INTEGER PRIMARY KEY ASC,
    date TEXT,
    time TEXT,
    description TEXT,
    local_filename TEXT,
    title TEXT,
    url_file TEXT,
    url TEXT,
    created_utc REAL,
    r_post_url TEXT,
    reddit_id TEXT,
    reddit_title TEXT,
    reddit_url TEXT,
    reddit_user TEXT,
    sgasm_user TEXT,
    subreddit_name TEXT);
    INSERT INTO my_table_copy (id, date, time, description, local_filename, title, url_file, url, created_utc, r_post_url,
                                reddit_id, reddit_title, reddit_url, reddit_user, sgasm_user, subreddit_name)
       SELECT rowid, Date, Time, Description, Local_filename, Title, URL, URLsg, created_utc, rPostUrl,
              redditID, redditTitle, redditURL, reddit_user, sgasm_user, subredditName FROM Downloads;
    DROP TABLE Downloads;
    ALTER TABLE my_table_copy RENAME TO Downloads;""")

conn.close()
