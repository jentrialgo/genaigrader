from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from genaigrader.models import Course, Evaluation, Exam, Model


class TooltipCountTest(TestCase):
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

        # Create 3 evaluations to verify count
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
        Evaluation.objects.create(
            exam=exam,
            model=model,
            prompt="Test prompt 3",
            ev_date="2024-01-03 14:00:00",
            grade=7.5,
            time=11.5,
        )

    def test_count_field_in_analysis_response(self):
        response = self.client.get(reverse("analysis"))
        self.assertEqual(response.status_code, 200)

        # Check that count field is present in overall_model_averages
        overall_model_averages = response.context["overall_model_averages"]
        self.assertGreater(
            len(overall_model_averages), 0, "Should have at least one model average"
        )

        test_model_data = None
        for model_data in overall_model_averages:
            if model_data["model__description"] == "Test Model":
                test_model_data = model_data
                break

        self.assertIsNotNone(test_model_data, "Should find Test Model in results")
        self.assertIn("count", test_model_data, "Count field should be present")
        self.assertEqual(
            test_model_data["count"], 3, "Count should be 3 for Test Model"
        )

        # Check course level data as well
        course_data = response.context["course_data"]
        test_course = None
        for course in course_data:
            if course["course"]["name"] == "Test Course":
                test_course = course
                break

        self.assertIsNotNone(test_course, "Should find Test Course in results")
        self.assertGreater(
            len(test_course["model_averages"]), 0, "Course should have model averages"
        )

        course_model_data = None
        for model_data in test_course["model_averages"]:
            if model_data["model__description"] == "Test Model":
                course_model_data = model_data
                break

        self.assertIsNotNone(
            course_model_data, "Should find Test Model in course results"
        )
        self.assertIn(
            "count", course_model_data, "Count field should be present in course data"
        )
        self.assertEqual(
            course_model_data["count"], 3, "Course count should be 3 for Test Model"
        )
