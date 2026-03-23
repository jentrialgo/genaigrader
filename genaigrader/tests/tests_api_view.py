from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from genaigrader.models import Model


class DeleteModelViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="admin", password="adminpass"
        )
        self.normal_user = User.objects.create_user(
            username="user", password="userpass"
        )
        self.model_instance = Model.objects.create(description="Test Model")
        self.url = reverse("delete_model", args=[self.model_instance.id])

    def test_superuser_can_delete_model(self):
        self.client.login(username="admin", password="adminpass")
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertFalse(Model.objects.filter(id=self.model_instance.id).exists())

    def test_non_superuser_cannot_delete_model(self):
        self.client.login(username="user", password="userpass")
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("Permission denied", response.json()["message"])
        self.assertTrue(Model.objects.filter(id=self.model_instance.id).exists())
