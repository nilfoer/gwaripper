import threading
import sqlite3

from flask import current_app

from gwaripper.db import load_or_create_sql_db


# Thread-local data is data whose values are thread specific. To manage thread-local data, just #
# create an instance of local (or a subclass) and store attributes on it
# t_local = threading.local()
# we get AttributeError: '_thread._local' object has no attribute 'mdb' if we didnt assign attr yet
# and it needs to be assigned for every thread separately -> better to subclass threading.local
class app_thread_data(threading.local):
    def __init__(self):
        super().__init__()
        self.db_init = False


t_local = app_thread_data()


def get_db():
    if not t_local.db_init:
        # cant store in app.config since thread specific and app config isnt
        t_local.db, _ = load_or_create_sql_db(current_app.config["DATABASE_PATH"])
        t_local.db.row_factory = sqlite3.Row
        t_local.db_init = True
    return t_local.db
