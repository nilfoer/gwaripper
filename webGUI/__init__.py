import os

from flask import Flask

from gwaripper.config import ROOTDIR

from .webGUI import main_bp, init_app
from .csrf import init_app as csrf_init_app
from .auth import auth_bp, init_app as auth_init_app


def create_app(test_config=None, **kwargs):
    # create and configure the app
    # configuration files are relative to the instance folder. The instance folder is located
    # outside the flaskr package and can hold local data that shouldn’t be committed to version
    # control, such as configuration secrets and the database file
    # default is app.root_path
    # we can define instance_path here as kwarg, default is instance (must be abspath)
    # -> so project_root/instance will be the instance folder depending on un/installed
    # module/package
    app = Flask(__name__, instance_relative_config=True,
                instance_path=ROOTDIR, **kwargs)
    # here root_path == N:\coding\tsu-info\manga_db\webGUI
    # instance_path == N:\coding\tsu-info\instance
    app.config.from_mapping(
        # unsafe key for dev purposes otherwise use true random bytes like:
        # python -c "import os; print(os.urandom(24))"
        SECRET_KEY='mangadb dev',
        DATABASE_PATH=os.path.join(app.instance_path, 'gwarip_db.sqlite'),
        # limit upload size to 0,5MB
        MAX_CONTENT_LENGTH=0.5 * 1024 * 1024
    )

    if test_config is None:
        # load the instance config (from instance folder since instance_relative.. is True),
        # if it exists, when not testing
        # The configuration file uses INI file syntax – name/value pairs in a plain text file,
        # separated by an equal sign =
        # TESTING=False
        # DEBUG=True
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        # test_config can also be passed to the factory, and will be used instead of the instance
        # configuration. This is so the tests you’ll write later in the tutorial can be configured
        # independently of any development values you have configured
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    csrf_init_app(app)
    init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    auth_init_app(app)

    return app
