import os
import importlib
import sqlite3
import logging
import shutil

logger = logging.getLogger(__name__)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# so we don't have to read all migration scripts every time
LATEST_VERSION = 2
VERSION_TABLE = 'GWAR_Version'
MIGRATIONS_DIRNAME = 'migrations'
# migrations dir has to be a sub-folder of the MODULE_DIR
MIGRATIONS_PATH = os.path.join(MODULE_DIR, MIGRATIONS_DIRNAME)

# NOTE: migrations file name pattern must be
# version_id padded with zeroes to 4 digits then an underscore followed by a migration name
# 0001_name.py
# a migration file only needs 2 things:
# a module-level variable 'date' with an iso8601 date string
# and an upgrade function that takes the db connection as its only parameter
# NOTE: IMPORANT migration scripts should never commit themselves!

# NOTE: if you change these you will have to also change the rest of the code
VERSION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
    version_id INTEGER PRIMARY KEY ASC,
    dirty INTEGER NOT NULL
    )"""

UPDATE_VERSION_SQL = f"""
UPDATE {VERSION_TABLE} SET
    version_id = :version,
    dirty = :dirty"""


class MigrationError(Exception):
    pass


class MigrationMissing(MigrationError):
    pass


class MigrationFailed(MigrationError):
    pass


class DatabaseError(MigrationError):
    pass


class Database:
    """
    Use Database as context manager!
    Changes will be automatically commited on success or rolled back on failure
    (including exceptions!)
    """

    def __init__(self, filename):
        self.filename = filename
        self.db_con = sqlite3.connect(filename)
        self.is_versionized = self._is_versionized()
        # NOTE: no prev version = -1
        self.version, self.is_dirty = self.get_version()
        self.transaction_in_progress = False
        self.migrations = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # If the context was exited without an exception, all three arguments will be None
        # if all((exc_type is None, exc_value is None, traceback is None)):
        # context manager just for automatically closing connection
        self._close()

    def __del__(self):
        self._close()

    def _is_versionized(self):
        version_tbl = self.db_con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                                          f"AND name = '{VERSION_TABLE}'").fetchone()
        if version_tbl:
            return True
        else:
            return False

    def _begin_transaction(self):
        if self.transaction_in_progress:
            raise DatabaseError("Another transaction is already in progress!")
        # NOTE: only read transactions allowed before this point (SELECT only)
        # exclusive transaction is a write transaction that even disallows read transactions
        # to allow them use 'IMMEDIATE'
        # implicit transaction (a transaction that is started automatically,
        # not a transaction started by BEGIN) is committed automatically when
        # the last active statement finishes
        # A statement finishes when its last cursor closes
        self.db_con.execute("BEGIN EXCLUSIVE TRANSACTION")
        self.transaction_in_progress = True

    def _create_version_table(self):
        self._begin_transaction()
        c = self.db_con.execute(VERSION_TABLE_SQL)
        c.execute(f"INSERT INTO {VERSION_TABLE} VALUES(-1, 0)")
        self.is_versionized = True
        self.version = -1
        self.is_dirty = False
        self._commit()

    def _commit(self):
        if self.transaction_in_progress:
            self.db_con.commit()
            self.transaction_in_progress = False
        else:
            raise DatabaseError("No transaction in progress")

    def _rollback(self):
        if self.transaction_in_progress:
            self.db_con.rollback()
            self.transaction_in_progress = False
            self.is_dirty = False
        else:
            raise DatabaseError("No transaction in progress")

    def _close(self):
        self.db_con.close()

    def get_version(self):
        if not self.is_versionized:
            return -1, False

        version_id, dirty = self.db_con.execute(
                f"SELECT version_id, dirty FROM {VERSION_TABLE}").fetchone()
        dirty = bool(dirty)
        return version_id, dirty

    def _upgrade_to_version(self, version):
        if (version - self.version) != 1:
            logger.error("Version %d (current) is not a direct sibling of %d!",
                         version, self.version)
            return False

        try:
            migration = self.migrations[version]
        except KeyError:
            raise MigrationMissing(f"No such version '{version}' available as migration!")
        else:
            migration.load_module()

            self._begin_transaction()
            self.is_dirty = True
            c = self.db_con.execute(UPDATE_VERSION_SQL,
                                    dict(version=migration.version_id,
                                         date=migration.date, dirty=1))
            try:
                migration.upgrade(self.db_con)
            except Exception:
                self._rollback()
                logger.error("Upgrading from version %d to %d failed! DB was rolled back!",
                             self.version, version)
                raise
            else:
                self.is_dirty = False
                c.execute(UPDATE_VERSION_SQL,
                          dict(version=migration.version_id,
                               date=migration.date, dirty=0))
                self._commit()
                self.version = version
                return True

    def upgrade_to_latest(self):
        if not self.is_versionized:
            self._create_version_table()

        backup_filename = f"{self.filename}.bak"
        if self.is_dirty:
            # TODO do this in enter or exit?
            if os.path.isfile(backup_filename):
                logger.error("DB is dirty! Restoring from back-up!")
                self.db_con.rollback()
                self.db_con.close()
                self.db_con = None
                os.remove(self.filename)
                shutil.copy(backup_filename, self.filename)
                self.__init__(self.filename)
            else:
                raise DatabaseError("Previous upgrade failed and there is no backup available!"
                                    "Aborting!")
        else:
            # make a backup just to be sure
            if self.version != LATEST_VERSION:
                # might have an old backup -> delete
                if os.path.exists(backup_filename):
                    os.remove(backup_filename)
                shutil.copy(self.filename, backup_filename)
            else:
                return True

        assert not self.is_dirty

        migrations = gather_migrations(self.version)
        if not migrations:
            raise MigrationMissing(
                    f"No migrations available to upgrade to latest version {LATEST_VERSION}!")
        self.migrations = migrations

        if self.version != LATEST_VERSION:
            logger.info("Migrating DB with version %d to newest version %d!",
                        self.version, LATEST_VERSION)

        # NOTE: _upgrade_to_version commits on success or rolls back on failure and exceptions
        while self.version != LATEST_VERSION:
            new_version = self.version + 1
            if not self._upgrade_to_version(new_version):
                return False
        else:
            # trigger manual VACUUM so db gets optimized after migrating it
            # The VACUUM command does not change the content of the database
            # except the rowid values. If you use INTEGER PRIMARY KEY column,
            # the VACUUM does not change the values of that column
            # good practice to run manually after deleting alot etc. -> so good
            # after migration
            # SQLite first copies data within a database file to a temporary
            # database. This operation defragments the database objects,
            # ignores the free spaces, and repacks individual pages.
            # then the result is copied back overwriting the original DB
            logger.info("Optimizing DB after migration!")
            self.db_con.execute("VACUUM")
            return True


class Migration:
    def __init__(self, filename):
        self.filename = filename
        self.version_id = int(filename.split('_', 1)[0])
        self.module = None
        self.loaded = False
        self.date = None
        self.upgrade = None

    def load_module(self):
        if not self.loaded:
            module_name = f".{MIGRATIONS_DIRNAME}.{self.filename.rsplit('.', 1)[0]}"
            try:
                self.module = importlib.import_module(module_name,
                                                      package=__package__)
            except ModuleNotFoundError:
                raise MigrationMissing(f"Migration {module_name} could not be imported!")

            self.loaded = True
            self.date = self.module.date
            self.upgrade = self.module.upgrade


# migrations folder needs to be a package (have a __init__.py) otherwise import_module
# won't work
# NOTE: the above used to be true but it was changed in py3.3 (PEP 420) where an implicit
# namespace package can be created from a folder without an __init__
# another option is that if no directory of the name is found but
# <directory>/foo.py(o/c/d..) the that module is returned
def gather_migrations(version=None):
    try:
        migrations = [Migration(fn) for fn in os.listdir(MIGRATIONS_PATH)
                      if fn[0] != '_' and fn.endswith('.py')]
    except FileNotFoundError:
        return {}
    else:
        if version is not None:
            return {m.version_id: m for m in migrations if m.version_id > version}
        else:
            return {m.version_id: m for m in migrations}
