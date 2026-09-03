# Copyright © 2017 Tom Hacohen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import signal
import sys
import threading
from functools import wraps
from urllib.parse import quote, urljoin, urlparse

import etesync as api
from flask import Flask, abort, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import PasswordField, StringField, URLField
from wtforms.validators import DataRequired, Optional, url

from etesync_dav.config import ETESYNC_URL, LEGACY_ETESYNC_URL, LISTEN_ADDRESS, LISTEN_PORT
from etesync_dav.local_cache import Etebase
from etesync_dav.mac_helpers import generate_cert, needs_ssl, trust_cert
from etesync_dav.manage import Manager

from .radicale.etesync_cache import etesync_for_user


class _LazyManager:
    """Create data files only when the web UI handles its first request."""

    def __init__(self):
        self._instance = None
        self._lock = threading.Lock()

    def __getattr__(self, name):
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = Manager()
        return getattr(self._instance, name)


manager = _LazyManager()


PORT = int(LISTEN_PORT)
BASE_URL = os.environ.get("ETESYNC_DAV_URL", "/")


def prefix_route(route_function, prefix="", mask="{0}{1}"):
    """
    Defines a new route function with a prefix.
    The mask argument is a `format string` formatted with, in that order:
      prefix, route
    """

    def newroute(route, *args, **kwargs):
        """New function to prefix the route"""
        return route_function(mask.format(prefix, route), *args, **kwargs)

    return newroute


# Special handling from frozen apps
if getattr(sys, "frozen", False):
    template_folder = os.path.join(sys._MEIPASS, "etesync_dav", "templates")
    app = Flask(__name__, template_folder=template_folder)
else:
    app = Flask(__name__)

app.route = prefix_route(app.route, "/.web")
app.config["TRUSTED_HOSTS"] = sorted({LISTEN_ADDRESS, "localhost", "127.0.0.1", "[::1]"})

app.secret_key = os.urandom(32)
CSRFProtect(app)


@app.context_processor
def inject_user():
    import etesync_dav

    return dict(version=etesync_dav.__version__)


def login_user(username):
    session["username"] = username


def logout_user():
    session.pop("username", None)


def logged_in():
    return "username" in session


def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not logged_in():
            # If we don't have any users, redirect to adding a user.
            if len(list(manager.list())) > 0:
                return redirect(url_for("login"))
            else:
                return redirect(url_for("add_user"))
        return func(*args, **kwargs)

    return decorated_view


def setup_or_login_required(func):
    """Allow unauthenticated access only while no account exists."""

    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not logged_in() and any(manager.list()):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return decorated_view


def dav_base_url():
    """Return the externally visible DAV root URL."""
    if urlparse(BASE_URL).scheme:
        return BASE_URL.rstrip("/") + "/"
    return urljoin(request.host_url, BASE_URL.lstrip("/"))


@app.route("/")
@login_required
def account_list():
    remove_user_form = UsernameForm(request.form)
    username = session["username"]
    password = manager.get(username)
    server_url_example = urljoin(dav_base_url(), f"{quote(username, safe='')}/")
    return render_template(
        "index.html",
        username=username,
        password=password,
        remove_user_form=remove_user_form,
        osx_ssl_warning=needs_ssl(),
        server_url_example=server_url_example,
    )


@app.route("/user/<string:user>")
@login_required
def user_index(user):
    if session["username"] != user:
        return redirect(url_for("user_index", user=session["username"]))
    type_name_mapper = {
        "etebase.vevent": "Calendars",
        "etebase.vtodo": "Tasks",
        "etebase.vcard": "Address Books",
    }
    collections = {}
    with etesync_for_user(user) as (etesync, _):
        if isinstance(etesync, Etebase):
            etesync.sync_collection_list()
            for col in etesync.list():
                col_type = type_name_mapper.get(col.col_type, None)
                if col_type is not None:
                    collections[col_type] = collections.get(col_type, [])
                    collections[col_type].append({"name": col.meta["name"], "uid": col.uid})
        else:
            etesync.sync_journal_list()
            journals = etesync.list()
            for journal in journals:
                collection = journal.collection
                collections[collection.TYPE] = collections.get(collection.TYPE, [])
                collections[collection.TYPE].append({"name": collection.display_name, "uid": journal.uid})

    return render_template(
        "user_index.html", BASE_URL=urljoin(dav_base_url(), f"{quote(user, safe='')}/"), collections=collections
    )


@app.route("/login/", methods=["GET", "POST"])
def login():
    if logged_in():
        return redirect(url_for("account_list"))

    errors = None
    form = LoginForm(request.form)
    if form.validate_on_submit():
        try:
            manager.check_login(form.username.data, form.login_password.data)
            login_user(form.username.data)
            return redirect(url_for("account_list"))
        except Exception:
            app.logger.exception("Account login failed")
            errors = "Login failed. Check the username, password, and server connection."
    else:
        errors = form.errors

    return render_template("login.html", form=form, errors=errors)


@app.route("/logout/", methods=["POST"])
@login_required
def logout():
    form = FlaskForm(request.form)
    if form.validate_on_submit():
        logout_user()

    return redirect(url_for("login"))


# FIXME: hack to kill server after generation.
def shutdown_response():
    from threading import Timer

    def shutdown():
        signal.raise_signal(signal.SIGTERM)

    thread = Timer(0.5, shutdown)
    thread.start()

    return redirect(url_for("shutdown_success"))


@app.route("/shutdown/", methods=["POST"])
@login_required
def shutdown():
    form = FlaskForm(request.form)
    if form.validate_on_submit():
        return shutdown_response()

    return redirect(url_for("login"))


@app.route("/shutdown/success/", methods=["GET"])
@login_required
def shutdown_success():
    return render_template("shutdown_success.html")


@app.route("/certgen/", methods=["GET", "POST"])
@login_required
def certgen():
    if request.method == "GET":
        return redirect(url_for("account_list"))

    form = FlaskForm(request.form)
    if form.validate_on_submit():
        generate_cert()
        trust_cert()

        return shutdown_response()

    return redirect(url_for("account_list"))


@app.route("/add/", methods=["GET", "POST"])
@setup_or_login_required
def add_user():
    errors = None
    form = AddUserForm(request.form)
    if form.validate_on_submit():
        try:
            server_url = form.server_url.data
            server_url = ETESYNC_URL if server_url == "" else server_url
            manager.add_etebase(form.username.data, form.login_password.data, server_url)
            return redirect(url_for("account_list"))
        except Exception:
            app.logger.exception("Adding an Etebase account failed")
            errors = "Could not add the account. Check the credentials, server URL, and connection."
    else:
        errors = form.errors

    return render_template("add_user.html", form=form, errors=errors)


@app.route("/add_legacy/", methods=["GET", "POST"])
@setup_or_login_required
def add_user_legacy():
    errors = None
    form = AddUserLegacyForm(request.form)
    if form.validate_on_submit():
        try:
            server_url = form.server_url.data
            server_url = LEGACY_ETESYNC_URL if server_url == "" else server_url
            manager.add(form.username.data, form.login_password.data, form.encryption_password.data, server_url)
            return redirect(url_for("account_list"))
        except api.exceptions.IntegrityException:
            errors = "Wrong encryption password (failed to decrypt data)"
        except Exception:
            app.logger.exception("Adding a legacy EteSync account failed")
            errors = "Could not add the account. Check the credentials, server URL, and connection."
    else:
        errors = form.errors

    return render_template("add_user_legacy.html", form=form, errors=errors)


@app.route("/remove_user/", methods=["GET", "POST"])
@login_required
def remove_user():
    form = UsernameForm(request.form)
    if form.validate_on_submit():
        if form.username.data != session["username"]:
            abort(403)
        manager.delete(form.username.data)
        logout_user()

    return redirect(url_for("login"))


class UsernameForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])


class LoginForm(UsernameForm):
    server_url = URLField("Server URL (Leave Empty for Default)", validators=[Optional(), url(require_tld=False)])
    login_password = PasswordField("Account Password", validators=[DataRequired()])


class AddUserForm(LoginForm):
    pass


class AddUserLegacyForm(LoginForm):
    encryption_password = PasswordField("Encryption Password", validators=[DataRequired()])


def run(debug=False):
    app.run(debug=debug, host=LISTEN_ADDRESS, port=PORT)
