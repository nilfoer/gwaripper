import secrets

from flask import (
        current_app, request, session,
        abort, Markup
        )


def init_app(app):
    @app.before_request
    def validate_csrf_token():
        # decorator @main_bp.before_request to execute this b4 every req
        # TODO add lifetime
        if request.method == "POST":
            token = session.get("_csrf_token", None)
            if not token:
                current_app.logger.error("Session is missing CSRF token!")
                abort(403)

            # is_xhr -> ajax request
            if request.is_xhr:
                # configured jquery ajax to send token as X-CSRFToken header
                if token != request.headers.get("X-CSRFToken", None):
                    current_app.logger.error("AJAX request CSRF token is invalid!")
                    abort(403)
            elif token != request.form.get("_csrf_token", None):
                current_app.logger.error("Request CSRF token is invalid!")
                abort(403)

    @app.after_request
    def reset_csrf_token(response):
        # since we save the csrf token in the session and flask session uses
        # itsdangerous.URLSafeTimedSerializer we dont need to change the token
        # every request to protect it against a BREACH (abusing gzip compression
        # when same or very similar data is sent over TLS) attack or reset it with
        # a salt so the transmitted value changes
        # -> so we only need to change it on login and logout and the session is cleared at
        #    that point anyways
        # -> BUT we need to re-set it every time so the session gets re-signed
        #    otherwise the exact same session cookie is transmitted
        token = session.get("_csrf_token", None)
        response.set_cookie('name', 'I am cookie')
        if token is not None:
            session["_csrf_token"] = token
        return response

    # register func to gen token field so we can us it in template
    app.jinja_env.globals['csrf_token_field'] = generate_csrf_token_field
    app.jinja_env.globals['csrf_token'] = generate_csrf_token


# partly taken from http://flask.pocoo.org/snippets/3/
def generate_csrf_token():
    if '_csrf_token' not in session:
        # As of 2015, it is believed that 32 bytes (256 bits) of randomness is sufficient for
        # the typical use-case expected for the secrets module
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


def generate_csrf_token_field():
    token = generate_csrf_token()
    return Markup(f"<input type='hidden' name='_csrf_token' value='{token}' />")


