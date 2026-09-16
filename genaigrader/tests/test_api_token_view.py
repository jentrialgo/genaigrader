from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class ApiTokenViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="tokenuser",
            email="token@example.com",
            password="password123",
        )
        self.url = reverse("api_token")

    def test_get_redirects_when_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_get_renders_token_when_authenticated(self):
        self.client.login(username="tokenuser", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.api_token)

    def test_get_renders_api_url_when_authenticated(self):
        self.client.login(username="tokenuser", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("api_url", response.context)
        self.assertTrue(response.context["api_url"].endswith("/api/v1/"))
        self.assertContains(response, response.context["api_url"])

    @override_settings(GENAIGRADER_API_URL="http://localhost:8000")
    def test_get_uses_env_api_url_when_setting_is_defined(self):
        self.client.login(username="tokenuser", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["api_url"], "http://localhost:8000/api/v1/")

    @override_settings(GENAIGRADER_API_URL="http://localhost:8000/")
    def test_get_strips_trailing_slash_from_env_api_url(self):
        self.client.login(username="tokenuser", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.context["api_url"], "http://localhost:8000/api/v1/")

    @override_settings(GENAIGRADER_API_URL=None)
    def test_get_falls_back_to_request_url_when_setting_is_none(self):
        self.client.login(username="tokenuser", password="password123")
        response = self.client.get(self.url)
        self.assertTrue(response.context["api_url"].endswith("/api/v1/"))

    def test_rotate_without_csrf_returns_403(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="tokenuser", password="password123")
        old_token = self.user.api_token
        response = csrf_client.post(self.url, {"action": "rotate"})
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.api_token, old_token)

    def test_rotate_with_csrf_changes_token(self):
        self.client.login(username="tokenuser", password="password123")
        old_token = self.user.api_token
        response = self.client.post(self.url, {"action": "rotate"})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.api_token, old_token)

    def test_old_token_invalid_after_rotate(self):
        self.client.login(username="tokenuser", password="password123")
        old_token = self.user.api_token
        self.client.post(self.url, {"action": "rotate"})
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.api_token, old_token)
        self.assertFalse(User.objects.filter(api_token=old_token).exists())
