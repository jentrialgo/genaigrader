from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.context import request_context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.signals import pre_social_login
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from users.adapters import AccountAdapter, SocialAccountAdapter, sync_external_identity
from users.models import CustomUser, ExternalIdentity

# --- ALLAUTH & LOCAL LOGIN TESTS ---


class AllauthLocalAuthTests(TestCase):
    def test_local_signup_creates_user(self) -> None:
        response = self.client.post(
            reverse("account_signup"),
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "S3curePass!123",
                "password2": "S3curePass!123",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(email="newuser@example.com")
        self.assertEqual(user.username, "newuser")

    def test_local_login_authenticates_with_email(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="legacyuser",
            email="legacy@example.com",
            password="S3curePass!123",
        )
        EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=True
        )

        response = self.client.post(
            reverse("account_login"),
            data={"login": "legacy@example.com", "password": "S3curePass!123"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_local_login_authenticates_with_username(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="legacyuser2",
            email="legacy2@example.com",
            password="S3curePass!123",
        )
        EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=True
        )

        response = self.client.post(
            reverse("account_login"),
            data={"login": "legacyuser2", "password": "S3curePass!123"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_local_signup_rejects_duplicate_email(self) -> None:
        user_model = get_user_model()
        user_model.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="S3curePass!123",
        )

        response = self.client.post(
            reverse("account_signup"),
            data={
                "username": "anotheruser",
                "email": "existing@example.com",
                "password1": "S3curePass!123",
                "password2": "S3curePass!123",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_login_page_hides_remember_and_password_reset(self) -> None:
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="remember"')
        self.assertNotContains(response, "/accounts/password/reset/")


# --- EXTERNAL IDENTITY & SOCIAL SYNC TESTS ---


class ExternalIdentitySyncTests(TestCase):
    def test_sync_external_identity_creates_and_updates(self) -> None:
        user_model = get_user_model()
        first_user = user_model.objects.create_user(
            username="oidcuser1",
            email="oidc1@example.com",
            password="S3curePass!123",
        )
        second_user = user_model.objects.create_user(
            username="oidcuser2",
            email="oidc2@example.com",
            password="S3curePass!123",
        )

        created = sync_external_identity(
            cast(
                SocialAccount,
                cast(
                    object,
                    SimpleNamespace(
                        provider="google",
                        uid="sub-123",
                        user=first_user,
                        extra_data={"sub": "sub-123", "name": "First"},
                    ),
                ),
            )
        )
        updated = sync_external_identity(
            cast(
                SocialAccount,
                cast(
                    object,
                    SimpleNamespace(
                        provider="google",
                        uid="sub-123",
                        user=second_user,
                        extra_data={"sub": "sub-123", "name": "Second"},
                    ),
                ),
            )
        )

        self.assertEqual(ExternalIdentity.objects.count(), 1)
        self.assertEqual(created.id, updated.id)
        self.assertEqual(updated.provider, ExternalIdentity.Provider.GOOGLE)
        self.assertEqual(updated.subject, "sub-123")
        self.assertEqual(updated.user_id, second_user.id)
        self.assertEqual(updated.extra_data["name"], "Second")

    def test_sync_external_identity_defaults_unknown_provider_to_oidc(self) -> None:
        user = get_user_model().objects.create_user(
            username="oidcdefault",
            email="oidcdefault@example.com",
            password="S3curePass!123",
        )

        identity = sync_external_identity(
            cast(
                SocialAccount,
                cast(
                    object,
                    SimpleNamespace(
                        provider="my_custom_provider",
                        uid="sub-999",
                        user=user,
                        extra_data={"sub": "sub-999"},
                    ),
                ),
            )
        )

        self.assertEqual(identity.provider, ExternalIdentity.Provider.OIDC)


class GoogleOAuthIntegrationTests(TestCase):
    def test_google_oauth_creates_external_identity(self) -> None:
        user_model = get_user_model()
        google_user = user_model.objects.create_user(
            username="googleuser",
            email="googleuser@example.com",
            password="S3curePass!123",
        )

        google_account = cast(
            SocialAccount,
            cast(
                object,
                SimpleNamespace(
                    provider="google",
                    uid="google-sub-12345",
                    user=google_user,
                    extra_data={
                        "sub": "google-sub-12345",
                        "name": "Google User",
                        "email": "googleuser@example.com",
                    },
                ),
            ),
        )

        identity = sync_external_identity(google_account)

        self.assertEqual(identity.provider, ExternalIdentity.Provider.GOOGLE)
        self.assertEqual(identity.subject, "google-sub-12345")
        self.assertEqual(identity.user_id, google_user.id)
        self.assertEqual(identity.extra_data["name"], "Google User")

    def test_pre_social_login_signal_syncs_missing_identity(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="test_prelogin",
            email="prelogin@example.com",
        )

        acc = SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-sub-9999",
            extra_data={"name": "PreLogin Google User"},
        )

        self.assertEqual(
            ExternalIdentity.objects.filter(subject="google-sub-9999").count(), 0
        )

        class MockSocialLogin:
            account = acc
            is_existing = True

        mock_login = MockSocialLogin()

        pre_social_login.send(
            sender=MockSocialLogin.__class__, request=None, sociallogin=mock_login
        )

        identity = ExternalIdentity.objects.get(subject="google-sub-9999")
        self.assertEqual(identity.provider, ExternalIdentity.Provider.GOOGLE)
        self.assertEqual(identity.user_id, user.id)
        self.assertEqual(identity.extra_data["name"], "PreLogin Google User")


# --- VALIDATION & AUTHENTICATION RULES TESTS ---


class AccountAdapterEmailValidationTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.factory = RequestFactory()

    def _clean_email_as(self, user: object, email: str) -> str:
        request = self.factory.get("/")
        request.user = user
        with request_context(request):
            adapter = AccountAdapter()
            return adapter.clean_email(email)

    def test_clean_email_allows_same_email_for_current_authenticated_user(self) -> None:
        current_user = self.user_model.objects.create_user(
            username="current-user",
            email="current@example.com",
            password="S3curePass!123",
        )
        result = self._clean_email_as(current_user, "CURRENT@example.com")
        self.assertEqual(result, "current@example.com")

    def test_clean_email_rejects_email_used_by_another_user(self) -> None:
        existing_user = self.user_model.objects.create_user(
            username="existing-user",
            email="existing@example.com",
            password="S3curePass!123",
        )
        requester_user = self.user_model.objects.create_user(
            username="requester-user",
            email="requester@example.com",
            password="S3curePass!123",
        )
        with self.assertRaises(ValidationError):
            self._clean_email_as(requester_user, existing_user.email)

    def test_clean_email_rejects_duplicate_for_anonymous_request(self) -> None:
        self.user_model.objects.create_user(
            username="existing-anon",
            email="existing-anon@example.com",
            password="S3curePass!123",
        )
        with self.assertRaises(ValidationError):
            self._clean_email_as(AnonymousUser(), "existing-anon@example.com")


class SingleAuthModeTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.factory = RequestFactory()

    def _request_with_session(self):
        request = self.factory.get("/")
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_local_auth_is_blocked_when_user_has_social_account(self) -> None:
        request = self._request_with_session()
        user = self.user_model.objects.create_user(
            username="social-only",
            email="social-only@example.com",
            password="S3curePass!123",
        )
        SocialAccount.objects.create(user=user, provider="google", uid="google-uid-1")

        adapter = AccountAdapter()
        with patch.object(DefaultAccountAdapter, "authenticate", return_value=user):
            result = adapter.authenticate(request, login=user.username, password="x")

        self.assertIsNone(result)

    def test_local_auth_works_for_pure_local_user(self) -> None:
        request = self._request_with_session()
        user = self.user_model.objects.create_user(
            username="local-only",
            email="local-only@example.com",
            password="S3curePass!123",
        )

        adapter = AccountAdapter()
        with patch.object(DefaultAccountAdapter, "authenticate", return_value=user):
            result = adapter.authenticate(request, login=user.username, password="x")

        self.assertEqual(result, user)

    def test_social_login_with_existing_email_is_blocked(self) -> None:
        user = self.user_model.objects.create_user(
            username="nolocal",
            email="nolocal@example.com",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        request = self._request_with_session()
        holder = SimpleNamespace(connect_called=False, connected_user_id=None)

        def _connect(_request, linked_user):
            holder.connect_called = True
            holder.connected_user_id = linked_user.id

        sociallogin = SimpleNamespace(
            is_existing=False,
            email_addresses=[
                SimpleNamespace(email="nolocal@example.com", verified=True)
            ],
            account=SimpleNamespace(
                provider="google", uid="google-uid-2", extra_data={}
            ),
            user=SimpleNamespace(email="nolocal@example.com"),
            connect=_connect,
            serialize=lambda: {
                "account": {"uid": "google-uid-2", "provider": "google"}
            },
        )

        with self.assertRaises(ImmediateHttpResponse):
            SocialAccountAdapter().pre_social_login(request, sociallogin)

        self.assertFalse(holder.connect_called)
        self.assertIsNone(holder.connected_user_id)

    def test_social_login_without_verified_email_is_blocked(self) -> None:
        request = self._request_with_session()
        holder = SimpleNamespace(connect_called=False)

        sociallogin = SimpleNamespace(
            is_existing=False,
            email_addresses=[SimpleNamespace(email="", verified=False)],
            account=SimpleNamespace(
                provider="google", uid="google-uid-3", extra_data={}
            ),
            user=SimpleNamespace(email=""),
            connect=lambda *_args, **_kwargs: setattr(holder, "connect_called", True),
        )

        with self.assertRaises(ImmediateHttpResponse):
            SocialAccountAdapter().pre_social_login(request, sociallogin)

        self.assertFalse(holder.connect_called)

    def test_social_linking_is_blocked_for_authenticated_user(self) -> None:
        authenticated_user = self.user_model.objects.create_user(
            username="already-authenticated",
            email="already-authenticated@example.com",
            password="S3curePass!123",
        )
        request = self._request_with_session()
        request.user = authenticated_user

        sociallogin = SimpleNamespace(
            is_existing=False,
            email_addresses=[
                SimpleNamespace(email="another@example.com", verified=True)
            ],
            account=SimpleNamespace(
                provider="google",
                uid="google-uid-4",
                extra_data={"email": "another@example.com", "email_verified": True},
            ),
            user=SimpleNamespace(email="another@example.com"),
            connect=lambda *_args, **_kwargs: None,
        )

        with self.assertRaises(ImmediateHttpResponse):
            SocialAccountAdapter().pre_social_login(request, sociallogin)


# --- USER SETTINGS & API TOKEN TESTS ---


class UserSettingsTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            # Cambiamos el dominio para esquivar el 'warning' de signals.py
            email="test@example.com",
            password="testpassword123",
        )
        self.client.login(username="testuser", password="testpassword123")


"""
    def test_update_profile_success(self):
        response = self.client.post(
            reverse("user_settings"),
            data={
                "username": "new_testuser",
                "first_name": "Alejandro",
                "last_name": "Rico"
            },
        )
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "new_testuser")
        self.assertEqual(self.user.first_name, "Alejandro")

    def test_update_profile_duplicate_username(self):
        CustomUser.objects.create_user(
            username="admin_existente",
            email="admin@genaigrader.local",
            password="password123"
        )

        response = self.client.post(
            reverse("user_settings"),
            data={
                "username": "admin_existente",
                "first_name": "Test",
                "last_name": "User"
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'username', 'A user with that username already exists.')

"""


class ApiTokenTests(TestCase):
    def test_api_token_generation_on_create(self):
        user = CustomUser.objects.create_user(
            username="apiuser", email="api@genaigrader.local", password="password123"
        )
        self.assertIsNotNone(user.api_token)
        self.assertEqual(len(user.api_token), 43)

    def test_rotate_api_token(self):
        user = CustomUser.objects.create_user(
            username="rotateuser",
            email="rotate@genaigrader.local",
            password="password123",
        )
        token_antiguo = user.api_token

        user.rotate_api_token()

        user.refresh_from_db()
        self.assertNotEqual(user.api_token, token_antiguo)
