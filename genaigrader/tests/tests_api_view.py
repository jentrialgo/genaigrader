from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from genaigrader.models import Model

User = get_user_model()


class DeleteModelViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass"
        )
        self.normal_user = User.objects.create_user(
            username="user", email="user@example.com", password="userpass"
        )
        self.model_instance = Model.objects.create(description="Test Model")
        self.url = reverse("delete_model", args=[self.model_instance.id])

    def test_superuser_can_delete_model(self):
        self.client.force_login(self.superuser)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertFalse(Model.objects.filter(id=self.model_instance.id).exists())

    def test_non_superuser_cannot_delete_model(self):
        self.client.force_login(self.normal_user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("Permission denied", response.json()["message"])
        self.assertTrue(Model.objects.filter(id=self.model_instance.id).exists())
