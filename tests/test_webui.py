from unittest import TestCase, mock

from etesync_dav import webui


class WebUiAuthorizationTest(TestCase):
    def setUp(self):
        webui.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = webui.app.test_client()
        self.manager_patch = mock.patch.object(webui, "manager")
        self.manager = self.manager_patch.start()

    def tearDown(self):
        self.manager_patch.stop()

    def login(self, username="alice"):
        with self.client.session_transaction() as session:
            session["username"] = username

    def test_existing_installation_requires_login_to_add_account(self):
        self.manager.list.return_value = iter(["alice"])

        response = self.client.get("/.web/add/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/.web/login/", response.location)

    def test_bootstrap_allows_first_account_form(self):
        self.manager.list.return_value = iter([])

        response = self.client.get("/.web/add/")

        self.assertEqual(response.status_code, 200)

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

    def test_dav_url_uses_request_host_and_escapes_username(self):
        self.login("alice@example.com")
        self.manager.get.return_value = "dav-password"

        response = self.client.get("/.web/", base_url="http://localhost:4567")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"http://localhost:4567/alice%40example.com/", response.data)
