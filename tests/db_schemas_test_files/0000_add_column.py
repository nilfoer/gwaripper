date = '2020-10-22'


def upgrade(db_con):
    db_con.execute("ALTER TABLE Downloads ADD COLUMN test TEXT NOT NULL DEFAULT 'migration success'")
