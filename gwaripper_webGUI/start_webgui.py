import sys

from typing import Optional, List

from . import create_app


def main(args: Optional[List[str]] = None):
    if args is None:
        args = sys.argv
    # use terminal environment vars to set debug etc.
    # windows: set FLASK_ENV=development -> enables debug or set FLASK_DEBUG=1
    app = create_app()

    port = 7568
    try:
        dash_p = args.index('-p')
    except ValueError:
        dash_p = None
    else:
        try:
            port = int(args[dash_p + 1])
            assert port > 1 and port < 65535 + 1
        except (IndexError, ValueError, AssertionError):
            print('-p port: Port must be an intger between 1 and 65535!')
            sys.exit(1)

    # use host='0.0.0.0' or ip to run on machine's ip address and be accessible over lan
    if 'open' in args:
        app.run(threaded=False, host='0.0.0.0', port=port)
    else:
        app.run(threaded=False, port=port)


if __name__ == "__main__":
    main()
