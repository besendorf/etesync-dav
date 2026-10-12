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

    def test_htpasswd_rejects_unsafe_usernames(self):
        unsafe_usernames = (
            "",
            " leading",
            "trailing ",
            "colon:name",
            "path/name",
            "path\\name",
            "line\nfeed",
            "carriage\rreturn",
            "null\0byte",
            "x" * 256,
        )
        with tempfile.TemporaryDirectory() as directory:
            password_file = Htpasswd(os.path.join(directory, "htpasswd"))
            for username in unsafe_usernames:
                with self.subTest(username=repr(username)), self.assertRaises(RuntimeError):
                    password_file.set(username, "password")

    def test_web_session_token_is_created_once_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            password_filename = os.path.join(directory, "htpasswd")
            credentials_filename = os.path.join(directory, "credentials.json")
            passwords = Htpasswd(password_filename)
            passwords.set("alice", "password")
            passwords.save()
            credentials = Credentials(credentials_filename)
            credentials.set_etebase("alice", "session", "https://example.com/")
            credentials.save()
            manager = Manager(
                config_dir=directory,
                htpasswd_file=password_filename,
                creds_file=credentials_filename,
            )

            with mock.patch("etesync_dav.manage.secrets.token_urlsafe", return_value="account-token") as token_urlsafe:
                first = manager.get_or_create_web_session_token("alice")
                second = manager.get_or_create_web_session_token("alice")

            self.assertEqual(first, "account-token")
            self.assertEqual(second, "account-token")
            token_urlsafe.assert_called_once_with(32)
            self.assertEqual(Credentials(credentials_filename).get_web_session_token("alice"), "account-token")

    def test_credential_refresh_preserves_web_session_token(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "credentials.json")
            credentials = Credentials(filename)
            credentials.set_etebase("alice", "old-session", "https://example.com/")
            credentials.set_web_session_token("alice", "account-token")
            credentials.set_etebase("alice", "new-session", "https://example.com/")

            self.assertEqual(credentials.get_web_session_token("alice"), "account-token")

    @mock.patch("etesync_dav.manage.secrets.choice", return_value="x")
    def test_generated_dav_password_uses_secrets(self, choice):
        password = Manager.__new__(Manager)._generate_password()

        self.assertEqual(password, "x" * 32)
        self.assertEqual(choice.call_count, 32)
