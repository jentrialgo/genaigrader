from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from genaigrader.models import Course, Evaluation, Exam, Model


class AnalysisViewTestWithoutDataTest(TestCase):
    def setUp(self):
        # Create a test user and log in
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.login(username="testuser", password="password")

    def test_course_without_exams_does_not_crash(self):
        # Create a course with no exams or evaluations
        Course.objects.create(user=self.user, name="Empty Course")

        # Call the analysis view
        response = self.client.get(reverse("analysis"))

        # Check response is 200 OK
        self.assertEqual(response.status_code, 200)

        # Verify context contains the course
        self.assertIn("course_data", response.context)
        course_data = response.context["course_data"]
        self.assertTrue(
            any(course["course"]["name"] == "Empty Course" for course in course_data)
        )

        # Check that model_averages and time_averages are empty
        empty_course = next(
            course
            for course in course_data
            if course["course"]["name"] == "Empty Course"
        )
        self.assertEqual(empty_course["model_averages"], [])
        self.assertEqual(empty_course["time_averages"], [])


class AnalysisViewTestWithDataTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.login(username="testuser", password="password")

        # Create related data
        course = Course.objects.create(name="Test Course", user=self.user)
        model = Model.objects.create(description="Test Model")
        exam = Exam.objects.create(
            course=course, description="Test Exam", user=self.user
        )

        # Create evaluations
        Evaluation.objects.create(
            exam=exam,
            model=model,
            prompt="Test prompt 1",
            ev_date="2024-01-01 10:00:00",
            grade=8.0,
            time=10.0,
        )
        Evaluation.objects.create(
            exam=exam,
            model=model,
            prompt="Test prompt 2",
            ev_date="2024-01-02 12:30:00",
            grade=9.0,
            time=12.0,
        )

    def test_analysis_view_context(self):
        response = self.client.get(reverse("analysis"))
        self.assertEqual(response.status_code, 200)

        # Check that key data is present in the response context
        self.assertIn("course_data", response.context)
        self.assertIn("overall_model_averages", response.context)
        self.assertIn("overall_time_averages", response.context)

        # Check that the expected model description appears in the model averages
        model_descriptions = [
            d["model__description"] for d in response.context["overall_model_averages"]
        ]
        self.assertIn("Test Model", model_descriptions)
