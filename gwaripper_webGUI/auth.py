import os.path
import functools
from flask import (
        Blueprint, request, redirect, url_for,
        render_template, flash, session, current_app
        )
from werkzeug.security import check_password_hash, generate_password_hash

ADMIN_CREDENTIALS_FN = "admin.txt"

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=("GET", 'POST'))
def register():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        error = None

        if "USERNAME" in current_app.config:
            error = "Only one user allowed at the moment!"
        elif not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'

        if error is None:
            pw_hash = generate_password_hash(password)
            with open(os.path.join(current_app.instance_path, ADMIN_CREDENTIALS_FN),
                      "w", encoding="UTF-8") as f:
                f.write(f"{username}\n{pw_hash}")
            # current_app is proxy to app handling current activity
            # used due to importing app leading to circ ref problems
            current_app.config["USERNAME"] = username
            current_app.config["PASSWORD"] = pw_hash
            return redirect(url_for('auth.login'))

        flash(error)

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None

        if "USERNAME" not in current_app.config:
            error = "No registered user!"
        elif username != current_app.config["USERNAME"] or (
                not check_password_hash(current_app.config['PASSWORD'], password)):
            error = 'Incorrect username or password.'

        if error is None:
            # clear session on login (among others for security reasons e.g.
            # if per-session-csrf token is used)
            session.clear()
            # only one user atm so we only care that hes logged in
            session['authenticated'] = True
            return redirect(url_for('main.show_entries'))

        flash(error)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    # clear session on logout to obv delete login-related info but also among others for
    # security reasons e.g. if per-session-csrf token is used)
    session.clear()
    return redirect(url_for('auth.login'))


# i could move all actions that need authentication to blueprints and
# then use blueprint.before_request to check for auth
def login_required(view):
    """This decorator returns a new view function that wraps the original view
    it’s applied to. The new function checks if a user is loaded and redirects
    to the login page otherwise."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "authenticated" not in session:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view


@auth_bp.before_request
def redirect_auth_users():
    if request.endpoint.endswith("logout"):
        # allow access to logout
        return
    # redirect authenticated users away from auth pages
    elif "authenticated" in session:
        return redirect(url_for('main.show_entries'))
    return


def init_app(app):
    admin_creds_path = os.path.join(app.instance_path, ADMIN_CREDENTIALS_FN)
    if os.path.isfile(admin_creds_path):
        with open(admin_creds_path, "r", encoding="UTF-8") as f:
            username, pw_hash = f.read().splitlines()
        app.config["USERNAME"] = username
        app.config["PASSWORD"] = pw_hash

    # check login on all pages but those that are marked is_public (by public_route decorator)
    # src: https://stackoverflow.com/a/52572337
    # Kristof Gilicze
    @app.before_request
    def check_route_access():
        if request.endpoint is None:  # can be None so check it first
            return
        if any([
                request.endpoint.startswith('static'),
                request.endpoint.startswith("thumb_static"),
                # auth/logout endpoint is auth.logout
                request.endpoint.startswith("auth."),  # allow access to auth pages by default
                "authenticated" in session,  # user is logged in
                # allow access to is_public marked functions
                getattr(app.view_functions[request.endpoint], 'is_public', False)]):
            return  # Access granted
        else:
            return redirect(url_for('auth.login'))


def public_route(decorated_function):
    decorated_function.is_public = True
    return decorated_function
