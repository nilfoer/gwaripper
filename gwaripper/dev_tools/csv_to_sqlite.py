import sqlite3
import pandas as pd
import os

def reorder_date(date_str):
    if "/" in date_str:
        l = date_str.split("/")
    elif "." in date_str:
        l = date_str.split(".")
    else:
        return date_str
    new_date_str = "{year}-{month}-{day}".format(year=l[2], month=l[1], day=l[0])
    return new_date_str

r_path = os.getcwd()  # "N:\_archive\\test\\trans\soundgasmNET\_dev"

df = pd.read_csv(os.path.join(r_path, "sgasm_rip_db.csv"), sep=";", encoding="utf-8", index_col=0)

# remove unnecessary \r added repeatedly by pandas during csv export
# use pd.Series.str.replace which applys it to every element and also uses regex
# replaces \r\r\r\r\n with \r\n
# df["Description"] = df["Description"].str.replace("\r+\n", "\r\n")
# pandas to_csv just adds one new extra \r -> rather remove all \r
df["Description"] = df["Description"].str.replace("\r", "")

# reorder date str (dd/mm/YYYY) to match sql format YYYY-mm-dd, time is already in correct format
df["Date"] = df["Date"].apply(reorder_date)

df.to_csv("sgasm_rip_db_rfix.csv", sep=";", encoding="utf-8")

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

# cur.execute("SELECT * FROM Downloads LIMIT 50")
# print(cur.fetchall())

conn.close()


