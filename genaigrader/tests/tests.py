from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from genaigrader.models import Course
from genaigrader.services.confidence_service import confidence_interval


class ExamViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="12345")
        # Crea datos de prueba
        self.course = Course.objects.create(name="Matemáticas", user=self.user)

    def test_exam_view_requires_login(self):
        response = self.client.get(reverse("evaluate"))
        self.assertEqual(response.status_code, 302)

    def test_exam_view_returns_200_for_logged_in_user(self):
        self.client.login(username="testuser", password="12345")
        response = self.client.get(reverse("evaluate"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "evaluate.html")
        self.assertContains(response, "Matemáticas")

    def test_exam_view_doesnt_contain_nonexistent_subject(self):
        self.client.login(username="testuser", password="12345")
        response = self.client.get(reverse("evaluate"))
        self.assertNotContains(response, "Sistemas Operativos")


class ConfidenceServiceTest(TestCase):
    def test_averages_two_values(self):
        data = [5, 10]
        mean, cinf, csup = confidence_interval(data, 0.95)
        self.assertEqual(mean, 7.5)
