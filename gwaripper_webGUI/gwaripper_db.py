import threading
import sqlite3

from flask import current_app, g

from gwaripper.db import load_or_create_sql_db


def get_db():
    # sqlite3 connections can't be shared between threads, but the module
    # can be used concurrently (assuming sqlite3.threadsafety>=1)
    # so every thread creates their own connection here
    # and stores it in the global app context g (which afaik is
    # threadlocal and every requrest is a new thread and  pushes
    # a new app context)
    if 'db' not in g:
        # cant store in app.config since thread specific and app config isnt
        g.db, _ = load_or_create_sql_db(
            current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db(app):
    @app.teardown_appcontext
    def teardown_db(exception):
        db = g.pop('db', None)

        if db is not None:
            db.close()
