from unittest import TestCase, mock

from etesync_dav import webui


class WebUiAuthorizationTest(TestCase):
    session_token = "web-session-token"

    def setUp(self):
        webui.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = webui.app.test_client()
        self.manager_patch = mock.patch.object(webui, "manager")
        self.manager = self.manager_patch.start()
        self.manager.get_web_session_token.return_value = self.session_token
        self.manager.get_or_create_web_session_token.return_value = self.session_token

    def tearDown(self):
        self.manager_patch.stop()

    def login(self, username="alice"):
        with self.client.session_transaction() as session:
            session["username"] = username
            session["web_session_token"] = self.session_token

    def test_existing_installation_requires_login_to_add_account(self):
        self.manager.list.return_value = ["alice"]

        response = self.client.get("/.web/add/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/.web/login/", response.location)

    def test_bootstrap_allows_first_account_form(self):
        self.manager.list.return_value = []

        response = self.client.get("/.web/add/")

        self.assertEqual(response.status_code, 200)

    def test_logged_in_user_cannot_add_another_account(self):
        self.login("alice")
        self.manager.list.return_value = ["alice"]

        response = self.client.post(
            "/.web/add/",
            data={
                "username": "bob",
                "login_password": "password",
                "server_url": "https://example.com",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.manager.add_etebase.assert_not_called()

    def test_logged_in_user_cannot_add_another_legacy_account(self):
        self.login("alice")
        self.manager.list.return_value = ["alice"]

        response = self.client.post(
            "/.web/add_legacy/",
            data={
                "username": "bob",
                "login_password": "password",
                "encryption_password": "encryption-password",
                "server_url": "https://example.com",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.manager.add.assert_not_called()

    def test_logged_in_user_cannot_delete_another_account(self):
        self.login("alice")

        response = self.client.post("/.web/remove_user/", data={"username": "bob"})

        self.assertEqual(response.status_code, 403)
        self.manager.delete.assert_not_called()

    def test_deleting_own_account_logs_out(self):
        self.login("alice")

        response = self.client.post("/.web/remove_user/", data={"username": "alice"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/.web/login/", response.location)
        self.manager.delete.assert_called_once_with("alice")
        with self.client.session_transaction() as session:
            self.assertNotIn("username", session)
            self.assertNotIn("web_session_token", session)

    def test_deleting_account_invalidates_other_sessions(self):
        tokens = {"alice": self.session_token}
        self.manager.get_web_session_token.side_effect = tokens.get
        self.manager.delete.side_effect = lambda username: tokens.pop(username)
        self.manager.list.return_value = ["bob"]
        other_client = webui.app.test_client()
        with other_client.session_transaction() as session:
            session["username"] = "alice"
            session["web_session_token"] = self.session_token
        self.login("alice")

        self.client.post("/.web/remove_user/", data={"username": "alice"})
        response = other_client.post("/.web/shutdown/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/.web/login/", response.location)

    def test_process_management_is_forbidden_with_multiple_accounts(self):
        self.login("alice")
        self.manager.list.return_value = ["alice", "bob"]

        shutdown_response = self.client.post("/.web/shutdown/")
        certificate_response = self.client.post("/.web/certgen/")

        self.assertEqual(shutdown_response.status_code, 403)
        self.assertEqual(certificate_response.status_code, 403)

    def test_sole_account_can_manage_process(self):
        self.login("alice")
        self.manager.list.return_value = ["alice"]
        with mock.patch.object(webui, "shutdown_response", return_value=("ok", 200)) as shutdown_response:
            response = self.client.post("/.web/shutdown/")

        self.assertEqual(response.status_code, 200)
        shutdown_response.assert_called_once_with()

    def test_login_records_account_session_token(self):
        self.manager.list.return_value = ["alice"]

        response = self.client.post(
            "/.web/login/",
            data={"username": "alice", "login_password": "password", "server_url": ""},
        )

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["username"], "alice")
            self.assertEqual(session["web_session_token"], self.session_token)

    def test_dav_url_uses_request_host_and_escapes_username(self):
        self.login("alice@example.com")
        self.manager.get.return_value = "dav-password"
        self.manager.list.return_value = ["alice@example.com"]

        response = self.client.get("/.web/", base_url="http://localhost:4567")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"http://localhost:4567/alice%40example.com/", response.data)
