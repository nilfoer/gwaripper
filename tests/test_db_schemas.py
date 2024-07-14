import pytest
import sys
import os
import datetime
import shutil
import sqlite3
import importlib
import re

from typing import Optional, List

import gwaripper.migrate as migrate

from utils import load_db_from_sql_file, TESTS_DIR, setup_tmpdir, load_db
from gwaripper.db import export_to_sql, load_or_create_sql_db


def test_export_to_sql(setup_tmpdir):
    tmpdir = setup_tmpdir

    sql_file = os.path.join(TESTS_DIR, "db_schemas_test_files", "gwarip_db.sqlite.sql")
    db_expected = load_db_from_sql_file(sql_file, ":memory:", True)
    db_expected.row_factory = None

    # same tables, indices and sql stmt
    c_exp = db_expected.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    expected = c_exp.fetchall()

    exported_sql = os.path.join(tmpdir, 'exported.sql')
    export_to_sql(exported_sql, db_expected)
    # export_to_sql uses sqlite3.Row check that it was reset
    assert db_expected.row_factory is None

    db_actual = load_db_from_sql_file(exported_sql, ":memory:", True)
    db_actual.row_factory = None

    # same tables, indices and sql stmt
    c_act = db_actual.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    actual = c_act.fetchall()
    assert expected == actual

    # technically already the same since we compare sql statements
    # same table setups: columns, types, nullable etc.
    for exp_row, act_row in zip(expected, actual):
        # Unfortunately pragma statements do not work with parameters
        exp_tbl = c_exp.execute(
                f"pragma table_info('{exp_row[2]}')").fetchall()
        act_tbl = c_act.execute(
                f"pragma table_info('{act_row[2]}')").fetchall()
        assert exp_tbl == act_tbl

    # compare all rows of all tables
    for sql_master_row in expected:
        if sql_master_row[0] != 'table':
            continue
        tbl_name = sql_master_row[2]

        expected = c_exp.execute(f"SELECT * FROM {tbl_name}").fetchall()
        actual = c_act.execute(f"SELECT * FROM {tbl_name}").fetchall()
        assert expected == actual


def test_db_migration(setup_tmpdir, monkeypatch, caplog):
    tmpdir = setup_tmpdir
    test_files = os.path.join(TESTS_DIR, 'db_schemas_test_files')

    migrations_dirname = 'migrations'
    tmp_migrations = os.path.join(tmpdir, migrations_dirname)
    # so importlib finds our 'package'
    sys.path.insert(0, tmpdir)
    monkeypatch.setattr("gwaripper.migrate.MODULE_DIR", tmpdir)
    monkeypatch.setattr("gwaripper.migrate.MIGRATIONS_PATH", tmp_migrations)
    monkeypatch.setattr("gwaripper.migrate.LATEST_VERSION", -1)

    tmp_db_fn = os.path.join(tmpdir, 'test.sqlite')
    db = load_db_from_sql_file(os.path.join(test_files, 'gwarip_db.sqlite.sql'),
                               tmp_db_fn)
    db.close()

    m = migrate.Database(tmp_db_fn)
    assert m.is_versionized is False
    assert m.is_dirty is False
    assert m.version == -1

    #
    # begin transaction, commit, rollback
    #
    with pytest.raises(migrate.DatabaseError, match='No transaction in progress'):
        m._commit()
    with pytest.raises(migrate.DatabaseError, match='No transaction in progress'):
        m._rollback()
    with pytest.raises(migrate.DatabaseError, match=r'Another transaction .* in progress'):
        m._begin_transaction()
        m._begin_transaction()
    m._rollback()
    with pytest.raises(sqlite3.OperationalError, match=r'.*database is locked.*'):
        # main attributes of err are .type, .value and .traceback
        m._begin_transaction()
        assert m.transaction_in_progress is True
        # 2nd param is timeout
        db = sqlite3.connect(tmp_db_fn, 0.1)
        db.execute("SELECT 1 FROM Downloads LIMIT 1")
    db.close()  # still needs to be closed even though no conection was established
    m._close()

    #
    # alrdy on latest version
    #

    m = migrate.Database(tmp_db_fn)
    assert m.upgrade_to_latest()
    assert m.is_versionized is True
    assert m._is_versionized()
    assert m.is_dirty is False
    assert m.version == -1
    m._close()

    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    migrated_db.close()
    assert len(rows) == 1
    assert rows[0][0] == -1
    assert rows[0][1] == 0

    #
    # check db gets closed when using 'with', last upgrade missing,
    # check bu old version, upgraded one version
    #

    os.makedirs(tmp_migrations)
    migration_0_fn = '0000_add_column.py'
    shutil.copy(os.path.join(test_files, migration_0_fn),
                tmp_migrations)

    monkeypatch.setattr("gwaripper.migrate.LATEST_VERSION", 1)

    unpatched_load_module = migrate.Migration.load_module

    def patched_load_module(self):
        self.module = importlib.import_module(
                f"{migrations_dirname}.{self.filename.rsplit('.', 1)[0]}")
        self.loaded = True
        self.date = self.module.date
        self.upgrade = self.module.upgrade

    monkeypatch.setattr("gwaripper.migrate.Migration.load_module", patched_load_module)

    unpatched_close = migrate.Database._close
    close_called = False

    def patched_close(x):
        nonlocal close_called
        close_called = True
        unpatched_close(x)

    monkeypatch.setattr("gwaripper.migrate.Database._close", patched_close)
    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == -1

        with pytest.raises(migrate.MigrationMissing, match=r"No such version '1'.*"):
            assert not m.upgrade_to_latest()
        assert os.path.isfile(tmp_db_fn + '.bak')
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

    assert close_called
    monkeypatch.setattr("gwaripper.migrate.Database._close", unpatched_close)

    # above updated to version 0
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    migrated_db.close()
    assert rows[0][0] == "migration success"

    # check backup
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == -1
    assert rows[0][1] == 0
    with pytest.raises(sqlite3.OperationalError):
        rows = migrated_db_bu.execute(
                "SELECT test FROM Downloads LIMIT 1").fetchall()
    migrated_db_bu.close()

    #
    # no migrations to upgrade to latest and already on latest available migration
    # + check backup removed and recopied
    #

    monkeypatch.setattr("gwaripper.migrate.LATEST_VERSION", 3)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(migrate.MigrationMissing,
                           match=r"No migrations available .* latest.*"):
            assert not m.upgrade_to_latest()
        assert os.path.isfile(tmp_db_fn + '.bak')
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

    # check backup of now current version
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    #
    # check rolled back changes on exception
    #

    unpatched_rollback = migrate.Database._rollback
    rollback_called = False

    def patched_rollback(x):
        nonlocal rollback_called
        rollback_called = True
        unpatched_rollback(x)

    monkeypatch.setattr("gwaripper.migrate.Database._rollback", patched_rollback)

    migration_1_fn = '0001_raises.py'
    shutil.copy(os.path.join(test_files, migration_1_fn),
                tmp_migrations)

    monkeypatch.setattr("gwaripper.migrate.LATEST_VERSION", 1)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(Exception, match='testing exception raised'):
            assert not m.upgrade_to_latest()
        assert rollback_called
        assert m.is_versionized is True
        assert m.is_dirty is False  # rollback resets this
        assert m.version == 0

    #
    # changes of renaming test column and updating version rolled back!!!
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    migrated_db.close()
    assert rows[0][0] == "migration success"

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    #
    # patch rollback so we can check that we flagged db as dirty etc.
    #
    rollback_called = False

    def patched_no_rollback(x):
        nonlocal rollback_called
        rollback_called = True
        x.db_con.commit()  # otherwise close just rolls back
        x.db_con.close()

    monkeypatch.setattr("gwaripper.migrate.Database._rollback", patched_no_rollback)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(Exception, match='testing exception raised'):
            assert not m.upgrade_to_latest()
        assert rollback_called
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 0

    #
    # new version and flagged as dirty
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 1
    rows = migrated_db.execute(
            "SELECT test FROM rolled_back LIMIT 1").fetchall()
    assert rows[0][0] == 'migration success'
    migrated_db.close()

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    monkeypatch.setattr("gwaripper.migrate.Database._rollback", unpatched_rollback)
    #
    # check that DB gets restored from backup if dirty!
    # + that upgrade fails if there is no backup
    #

    # overwrite exception raising migration
    with open(os.path.join(tmp_migrations, migration_1_fn), 'w') as f:
        f.write("date = '2020-10-24'\ndef upgrade(db_con):\n"
                "  db_con.execute('CREATE TABLE no_exc(name TEXT)')\n"
                "  db_con.execute('INSERT INTO no_exc VALUES(\\'no exec raised\\')')")
    # needs to be reloaded otherwise cached version will be used
    importlib.reload(m.migrations[1].module)

    # rename backup file to test if upgrading gets aborted
    os.rename(os.path.join(tmpdir, f"{tmp_db_fn}.bak"),
              os.path.join(tmpdir, 'renamed.bak'))

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

        with pytest.raises(migrate.DatabaseError, match=r'.*upgrade failed.*no backup.*Aborting!'):
            assert not m.upgrade_to_latest()
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

    #
    # new version and flagged as dirty
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 1
    rows = migrated_db.execute(
            "SELECT test FROM rolled_back LIMIT 1").fetchall()
    assert rows[0][0] == 'migration success'
    migrated_db.close()

    # rename back
    os.rename(os.path.join(tmpdir, 'renamed.bak'),
              os.path.join(tmpdir, f"{tmp_db_fn}.bak"))

    caplog.clear()

    #
    # continue with backup
    #

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

        assert m.upgrade_to_latest()
        # TODO
        assert "DB is dirty! Restoring from back-up!" in caplog.text
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 1
        # db vacuumed
        assert "Optimizing DB after migration" in caplog.text

    #
    # new version
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT name FROM no_exc").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 'no exec raised'
    migrated_db.close()

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Downloads LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()


def clean_sql(sql: Optional[str]) -> Optional[List[str]]:
    if not sql:
        return None
    sql_comment = re.compile(r'--.*')
    sql = re.sub(sql_comment, "", sql)
    words = sql.split()
    cleaned = []
    # remove quoted table names
    for word in words:
        print(word)
        match = re.match(r'"(\w+)"(\(.*)', word)
        if match:
            print(match)
            cleaned.append(f"{match.group(1)}{match.group(2)}")
        else:
            cleaned.append(word)
    return cleaned


def test_db_migration_to_latest_same_as_create(setup_tmpdir):
    tmpdir = setup_tmpdir

    tmp_migrated_db_fn = os.path.join(tmpdir, 'migrated.sqlite')
    db_migrated = sqlite3.connect(tmp_migrated_db_fn)
    # v -1 creation statement
    db_migrated.executescript("""
    BEGIN TRANSACTION;
    PRAGMA foreign_keys=off;
    CREATE VIRTUAL TABLE Downloads_fts_idx USING fts5(
              title, reddit_title, content='Downloads', content_rowid='id');
    CREATE TABLE "Downloads"(
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
        subreddit_name TEXT, rating REAL, favorite INTEGER DEFAULT 0 NOT NULL);
    CREATE TRIGGER Downloads_au AFTER UPDATE ON Downloads BEGIN
              INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
              VALUES('delete', old.id, old.title, old.reddit_title);
              INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
              VALUES (new.id, new.title, new.reddit_title);
            END;
    CREATE TRIGGER Downloads_ad AFTER DELETE ON Downloads BEGIN
                  INSERT INTO Downloads_fts_idx(Downloads_fts_idx, rowid, title, reddit_title)
                  VALUES('delete', old.id, old.title, old.reddit_title);
                END;
    CREATE TRIGGER Downloads_ai AFTER INSERT ON Downloads BEGIN
                  INSERT INTO Downloads_fts_idx(rowid, title, reddit_title)
                  VALUES (new.id, new.title, new.reddit_title);
                END;
    PRAGMA foreign_keys=on;
    COMMIT;""")

    with migrate.Database(tmp_migrated_db_fn) as m:
        m.upgrade_to_latest()

    tmp_db_fn = os.path.join(tmpdir, 'created.sqlite')
    db_created, _ = load_or_create_sql_db(tmp_db_fn)

    #
    # comparing same db setup
    # (not migrating rows or comparing same rows)
    #
    db_created.row_factory = None
    c_expected = db_created.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    expected = c_expected.fetchall()
    db_migrated.row_factory = None
    # same tables, indices and sql stmt
    c_actual = db_migrated.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    actual = c_actual.fetchall()
    expected = [(_type, tbl_name, name, clean_sql(sql)) for _type, tbl_name, name, sql in expected]
    actual = [(_type, tbl_name, name, clean_sql(sql)) for _type, tbl_name, name, sql in actual]
    assert expected == actual

    # technically already the same since we compare sql statements
    # same table setups: columns, types, nullable etc.
    for exp_row, act_row in zip(expected, actual):
        # Unfortunately pragma statements do not work with parameters
        exp_tbl = c_expected.execute(
                f"pragma table_info('{exp_row[2]}')").fetchall()
        act_tbl = c_actual.execute(
                f"pragma table_info('{act_row[2]}')").fetchall()
        assert exp_tbl == act_tbl


def test_db_constraints(setup_tmpdir):
    tmpdir = setup_tmpdir

    test_db_fn = os.path.join(tmpdir, 'test_db.sqlite')
    db_con, c = load_or_create_sql_db(test_db_fn)

    #
    # AudioFile
    #

    # collection_id FK FileCollection(id)
    # (alias UNKNOWN_USR_FOLDER and DELETED_USR_FOLDER are inserted by default)
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY constraint failed'):
        # inserting with invalid collection_id
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(collection_id, date, filename, url, alias_id)
            VALUES (4, '2020-05-12', 'asf', 'sadfsadf', 1);
        """)

    db_con.rollback()

    # date NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: AudioFile.date'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES (NULL, 'asf', 'sadfsadf', 1);
        """)

    db_con.rollback()

    # filename NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: AudioFile.filename'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES ('2020-12-12', NULL, 'sadfsadf', 1);
        """)

    db_con.rollback()

    # url UNIQUE NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='UNIQUE constraint failed: AudioFile.url'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES ('2020-12-12', 'filename', 'url', 1);
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES ('2020-12-12', 'filename', 'url', 1);
        """)

    db_con.rollback()

    # alias_id NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: AudioFile.alias_id'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES ('2020-12-12', 'filename', 'url', NULL);
        """)

    db_con.rollback()

    # alias_id FK Alias(id)
    with pytest.raises(
            sqlite3.IntegrityError,
            match='FOREIGN KEY constraint failed'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO AudioFile(date, filename, url, alias_id)
            VALUES ('2020-12-12', 'filename', 'url', 2384);
        """)

    db_con.rollback()

    #
    # Artist
    #

    # name UNIQUE
    with pytest.raises(
            sqlite3.IntegrityError,
            match='UNIQUE constraint failed: Artist.name'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO Artist(name) VALUES ('asdf');
        INSERT INTO Artist(name) VALUES ('asdf');
        """)

    db_con.rollback()

    #
    # Alias
    #

    # name UNIQUE
    with pytest.raises(
            sqlite3.IntegrityError,
            match='UNIQUE constraint failed: Alias.name'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO Alias(name) VALUES ('asdf');
        INSERT INTO Alias(name) VALUES ('asdf');
        """)

    db_con.rollback()

    # name NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: Alias.name'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO Alias(name) VALUES (NULL);
        """)

    db_con.rollback()

    # artist_id FK Artist(id)
    with pytest.raises(
            sqlite3.IntegrityError,
            match='FOREIGN KEY constraint failed'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO Alias(name, artist_id) VALUES ('afsdf', 2343);
        """)

    db_con.rollback()

    #
    # FileCollection
    #

    # url UNIQUE
    with pytest.raises(
            sqlite3.IntegrityError,
            match='UNIQUE constraint failed: FileCollection.url'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', NULL, NULL, 1);
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', NULL, NULL, 1);
        """)

    db_con.rollback()

    # url NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: FileCollection.url'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES (NULL, 'subpath', NULL, NULL, 1);
        """)

    db_con.rollback()

    # subpath NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: FileCollection.subpath'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', NULL, NULL, NULL, 1);
        """)

    db_con.rollback()

    # reddit_info_id FK RedditInfo(id)
    with pytest.raises(
            sqlite3.IntegrityError,
            match='FOREIGN KEY constraint failed'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', 242, NULL, 1);
        """)

    db_con.rollback()

    # parent_id FK FileCollection(id)
    with pytest.raises(
            sqlite3.IntegrityError,
            match='FOREIGN KEY constraint failed'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', NULL, 435, 1);
        """)

    db_con.rollback()
    
    # alias_id NOT NULL
    with pytest.raises(
            sqlite3.IntegrityError,
            match='NOT NULL constraint failed: FileCollection.alias_id'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', NULL, NULL, NULL);
        """)

    db_con.rollback()

    # alias_id FK Alias(id)
    with pytest.raises(
            sqlite3.IntegrityError,
            match='FOREIGN KEY constraint failed'):
        c.executescript("""
        BEGIN TRANSACTION;
        INSERT INTO FileCollection(url, subpath, reddit_info_id, parent_id, alias_id)
            VALUES ('url', 'subpath', NULL, NULL, 1309);
        """)

    db_con.rollback()


def test_gather_migrations(setup_tmpdir, monkeypatch):
    tmpdir = setup_tmpdir

    monkeypatch.setattr("gwaripper.migrate.MODULE_DIR", tmpdir)
    monkeypatch.setattr("gwaripper.migrate.MIGRATIONS_PATH", tmpdir)

    # create a bunch of empty files in the migration dir
    open(os.path.join(tmpdir, '__init__.py'), 'w').close()
    open(os.path.join(tmpdir, '_private.py'), 'w').close()
    open(os.path.join(tmpdir, '0000_zero.py'), 'w').close()
    open(os.path.join(tmpdir, '0001_one.py'), 'w').close()
    open(os.path.join(tmpdir, '0002_two.py'), 'w').close()
    open(os.path.join(tmpdir, '0003_three.py'), 'w').close()
    open(os.path.join(tmpdir, '0004_four.py'), 'w').close()
    open(os.path.join(tmpdir, '0005_five.py'), 'w').close()
    open(os.path.join(tmpdir, '5432_test.py'), 'w').close()
    open(os.path.join(tmpdir, '1234_7894_test.py'), 'w').close()
    open(os.path.join(tmpdir, 'other.pyc'), 'w').close()
    open(os.path.join(tmpdir, 'other.txt'), 'w').close()
    open(os.path.join(tmpdir, 'other.ini'), 'w').close()

    migrations = migrate.gather_migrations()

    found = [
             '0000_zero.py',
             '0001_one.py',
             '0002_two.py',
             '0003_three.py',
             '0004_four.py',
             '0005_five.py',
             '1234_7894_test.py',
             '5432_test.py']
    assert type(migrations) is dict
    assert sorted([migrations[v].filename for v in migrations]) == sorted(found)

    for v in range(6):
        assert migrations[v].version_id == v and migrations[v].filename == found[v]
    v = 1234
    assert migrations[v].version_id == v and migrations[v].filename == found[6]
    v = 5432
    assert migrations[v].version_id == v and migrations[v].filename == found[7]

    migrations = migrate.gather_migrations(version=3)

    found = [
             '0004_four.py',
             '0005_five.py',
             '1234_7894_test.py',
             '5432_test.py']
    assert type(migrations) is dict
    assert sorted([migrations[v].filename for v in migrations]) == sorted(found)

    v = 4
    assert migrations[v].version_id == v and migrations[v].filename == found[0]
    v = 5
    assert migrations[v].version_id == v and migrations[v].filename == found[1]
    v = 1234
    assert migrations[v].version_id == v and migrations[v].filename == found[2]
    v = 5432
    assert migrations[v].version_id == v and migrations[v].filename == found[3]
