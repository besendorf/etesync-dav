import json
import os
import sqlite3
import tempfile
from unittest import TestCase, mock

from etesync_dav.radicale.storage import Storage


class StorageTest(TestCase):
    def test_anonymous_storage_lock_is_a_valid_context_manager(self):
        storage = Storage.__new__(Storage)

        with storage.acquire_lock("r"):
            pass

    def test_storage_verification_checks_account_files_and_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = os.path.join(directory, "credentials.json")
            passwords = os.path.join(directory, "htpasswd")
            database = os.path.join(directory, "cache.db")
            with open(credentials, "w", encoding="utf-8") as output:
                json.dump({"users": {"alice": {"storedSession": "session"}}}, output)
            with open(passwords, "w", encoding="utf-8") as output:
                output.write("alice:password\n")
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE sample (value TEXT)")
                connection.commit()
            finally:
                connection.close()

            with (
                mock.patch("etesync_dav.radicale.storage.CREDS_FILE", credentials),
                mock.patch("etesync_dav.radicale.storage.HTPASSWD_FILE", passwords),
                mock.patch("etesync_dav.radicale.storage.DATABASE_FILE", database),
                mock.patch("etesync_dav.radicale.storage.ETEBASE_DATABASE_FILE", os.path.join(directory, "missing.db")),
            ):
                self.assertTrue(Storage.__new__(Storage).verify())

    def test_storage_verification_rejects_mismatched_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = os.path.join(directory, "credentials.json")
            passwords = os.path.join(directory, "htpasswd")
            with open(credentials, "w", encoding="utf-8") as output:
                json.dump({"users": {"alice": {"storedSession": "session"}}}, output)
            with open(passwords, "w", encoding="utf-8") as output:
                output.write("bob:password\n")

            with (
                mock.patch("etesync_dav.radicale.storage.CREDS_FILE", credentials),
                mock.patch("etesync_dav.radicale.storage.HTPASSWD_FILE", passwords),
                mock.patch("etesync_dav.radicale.storage.DATABASE_FILE", os.path.join(directory, "missing-1.db")),
                mock.patch(
                    "etesync_dav.radicale.storage.ETEBASE_DATABASE_FILE", os.path.join(directory, "missing-2.db")
                ),
            ):
                self.assertFalse(Storage.__new__(Storage).verify())

    def test_unsupported_writes_return_permission_errors(self):
        storage = Storage.__new__(Storage)

        with self.assertRaisesRegex(ValueError, "Errno 13"):
            storage.create_collection("/alice/calendar")
        with self.assertRaisesRegex(ValueError, "Errno 13"):
            storage.move(None, None, "item.ics")
