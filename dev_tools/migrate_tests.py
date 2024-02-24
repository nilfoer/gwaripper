import sys
import os
import shutil
import glob

MODULE_DIR = os.path.abspath(os.path.dirname(__file__))

sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..')))
sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..', 'tests')))

import gwaripper.migrate as migrate

from gwaripper.db import db_to_sql_insert_only, load_or_create_sql_db
from utils import load_db_from_sql_file, setup_tmpdir


if len(sys.argv) > 1:
    if sys.argv[1] == "revert":
        for fn in [f for patt in ['tests/all_test_files/*.old.sql'] for f in glob.glob(patt)]:
            replace_fn = f"{fn.rsplit('.', 2)[0]}.sql"
            os.remove(replace_fn)
            os.rename(fn, replace_fn)
            print("Restored", fn)
    elif sys.argv[1] == "cleanup":
        ans = True if input("Are you sure? y/n\n").lower() in ('y', 'yes') else False
        if not ans:
            sys.exit(0)
        for fn in [f for patt in ['tests/all_test_files/*.old.sql'] for f in glob.glob(patt)]:
            os.remove(fn)
            print("Deleted", fn)

    sys.exit(0)

tmpdir = os.path.join(MODULE_DIR, 'tmp')
try:
    shutil.rmtree(tmpdir)
except FileNotFoundError:
    pass
os.makedirs(tmpdir)

for fn in [f for patt in ['tests/all_test_files/*.sql'] for f in glob.glob(patt)]:
    if 'db_schemas' in fn:
        # NOTE: IMPORTANT never migrate migration test sql file
        assert False

    db_fn = os.path.join(tmpdir, fn.replace(os.sep, '_').replace(os.altsep, '_'))
    print('Migrating test sql file:', fn)

    temp_db_file = fn + "_tmp.sqlite"
    db_con, _ = load_or_create_sql_db(temp_db_file)
    # remove version so correct one gets inserted
    db_con.execute(f"DELETE FROM {migrate.VERSION_TABLE}")

    with open(fn, "r", encoding="UTF-8") as f:
        sql = f.read()

    db_con.executescript(sql)

    db_con.close()

    migrate_db = migrate.Database(temp_db_file)
    assert migrate_db.upgrade_to_latest()
    os.rename(fn, f"{fn[:-4]}.old.sql")
    # @Hack using migrate_db's db_con
    res = db_to_sql_insert_only(migrate_db.db_con).splitlines()
    migrate_db._close()

    # @Hack removing first two Alias rows, since they get inserted by load_or_create_sql_db
    for i in range(len(res)):
        line = res[i].strip()
        if line.startswith("INSERT INTO \"Alias"):
            del res[i+1]
            del res[i+1]
            break

    # @Hack change version to use update instead of insert
    version_idx = next(i for i in range(len(res))
                       if res[i].startswith(f'INSERT INTO "{migrate.VERSION_TABLE}'))
    version = res[version_idx + 1][1:].split(',')[0]
    res[version_idx] = f'UPDATE "{migrate.VERSION_TABLE}" SET'
    res[version_idx + 1] = f'version_id = {version}, dirty = 0;'

    with open(fn, 'w', encoding='UTF-8') as f:
        f.write("\n".join(res))

    os.remove(temp_db_file)
    try:
        os.remove(temp_db_file + ".bak")
    except FileNotFoundError:
        pass

shutil.rmtree(tmpdir)
