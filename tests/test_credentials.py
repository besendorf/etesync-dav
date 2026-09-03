import json
import os
import tempfile
from unittest import TestCase, mock

from etesync_dav.fileutils import open_log_file
from etesync_dav.manage import Htpasswd, Manager
from etesync_dav.radicale.creds import Credentials


class CredentialsTest(TestCase):
    def test_log_file_parent_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "missing", "etesync-dav.log")
            log_file = open_log_file(filename, directory)
            self.assertIsNotNone(log_file)
            log_file.close()
            self.assertTrue(os.path.isfile(filename))

    def test_credentials_are_atomically_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "credentials.json")
            credentials = Credentials(filename)
            credentials.set_etebase("alice", "session", "https://example.com/")
            credentials.save()

            with open(filename, encoding="utf-8") as saved:
                self.assertEqual(json.load(saved)["users"]["alice"]["storedSession"], "session")
            self.assertEqual(list(filter(lambda name: name.startswith(".etesync-dav-"), os.listdir(directory))), [])

    def test_separate_instances_merge_account_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "credentials.json")
            first = Credentials(filename)
            second = Credentials(filename)

            first.set_etebase("alice", "session-a", "https://example.com/")
            second.set_etebase("bob", "session-b", "https://example.com/")
            first.save()
            second.save()

            saved = Credentials(filename)
            self.assertEqual(set(saved.list()), {"alice", "bob"})

    def test_htpasswd_ignores_blank_lines_and_rejects_malformed_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "htpasswd")
            with open(filename, "w", encoding="utf-8") as password_file:
                password_file.write("alice:secret\n\n")
            self.assertEqual(Htpasswd(filename).get("alice"), "secret")

            with open(filename, "w", encoding="utf-8") as password_file:
                password_file.write("malformed\n")
            with self.assertRaisesRegex(ValueError, "Malformed password entry"):
                Htpasswd(filename)

    def test_separate_htpasswd_instances_merge_account_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "htpasswd")
            first = Htpasswd(filename)
            second = Htpasswd(filename)

            first.set("alice", "password-a")
            second.set("bob", "password-b")
            first.save()
            second.save()

            self.assertEqual(set(Htpasswd(filename).list()), {"alice", "bob"})

    @mock.patch("etesync_dav.manage.secrets.choice", return_value="x")
    def test_generated_dav_password_uses_secrets(self, choice):
        password = Manager.__new__(Manager)._generate_password()

        self.assertEqual(password, "x" * 32)
        self.assertEqual(choice.call_count, 32)
