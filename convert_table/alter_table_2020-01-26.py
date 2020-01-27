import sqlite3

db_con = sqlite3.connect("./gwarip_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                ALTER TABLE Downloads ADD COLUMN rating REAL;
                ALTER TABLE Downloads ADD COLUMN favorite INTEGER DEFAULT 0 NOT NULL;

                COMMIT;

                PRAGMA foreign_keys=on;
                """)
