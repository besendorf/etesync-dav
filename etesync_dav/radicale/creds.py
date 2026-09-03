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

import base64
import json
import os

from etesync_dav.config import LEGACY_ETESYNC_URL
from etesync_dav.fileutils import atomic_write_text, locked_path


class Credentials:
    def __init__(self, filename):
        self.filename = filename
        self.last_mtime = 0
        self.content = {"users": {}}
        self._dirty_users = set()
        self._deleted_users = set()
        self.load()

    def _read_users(self):
        if not os.path.exists(self.filename):
            return {}
        with open(self.filename, "r", encoding="utf-8") as f:
            return json.load(f).get("users", {})

    def load(self):
        with locked_path(self.filename):
            if os.path.exists(self.filename):
                mtime = os.path.getmtime(self.filename)
                if mtime != self.last_mtime:
                    pending = {username: self.content["users"][username] for username in self._dirty_users}
                    users = self._read_users()
                    users.update(pending)
                    for username in self._deleted_users:
                        users.pop(username, None)
                    self.content = {"users": users}
                self.last_mtime = mtime

    def save(self):
        with locked_path(self.filename):
            users = self._read_users()
            users.update({username: self.content["users"][username] for username in self._dirty_users})
            for username in self._deleted_users:
                users.pop(username, None)
            self.content = {"users": users}
            atomic_write_text(self.filename, json.dumps(self.content, separators=(",", ":")))
            self.last_mtime = os.path.getmtime(self.filename)
            self._dirty_users.clear()
            self._deleted_users.clear()

    def get_server_url(self, username):
        users = self.content["users"]
        if username not in users:
            return None

        user = users[username]
        return user.get("serverUrl", LEGACY_ETESYNC_URL)

    def get(self, username):
        users = self.content["users"]
        if username not in users:
            return None, None

        user = users[username]
        return user["authToken"], base64.b64decode(user["cipherKey"])

    def set(self, username, auth_token, cipher_key, server_url):
        users = self.content["users"]
        user = {"authToken": auth_token, "cipherKey": base64.b64encode(cipher_key).decode(), "serverUrl": server_url}
        users[username] = user
        self._dirty_users.add(username)
        self._deleted_users.discard(username)

    def get_etebase(self, username):
        users = self.content["users"]
        if username not in users:
            return None

        user = users[username]
        return user.get("storedSession", None)

    def set_etebase(self, username, stored_session, server_url):
        users = self.content["users"]
        user = {"storedSession": stored_session, "serverUrl": server_url}
        users[username] = user
        self._dirty_users.add(username)
        self._deleted_users.discard(username)

    def delete(self, username):
        users = self.content["users"]
        users.pop(username, None)
        self._dirty_users.discard(username)
        self._deleted_users.add(username)

    def list(self):
        yield from self.content["users"]
