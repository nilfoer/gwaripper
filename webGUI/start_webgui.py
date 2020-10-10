import sys

from . import create_app


def main():
    # use terminal environment vars to set debug etc.
    # windows: set FLASK_ENV=development -> enables debug or set FLASK_DEBUG=1
    app = create_app()
    # use threaded=False so we can leverage MangaDB's id_map
    # also makes sense since we only want to support one user (at least with write access)
    # use host='0.0.0.0' or ip to run on machine's ip address and be accessible over lan
    if len(sys.argv) > 1 and sys.argv[1] == "open":
        app.run(threaded=False, host='0.0.0.0', port=7568)
    else:
        app.run(threaded=False, port=7568)


if __name__ == "__main__":
    main()
