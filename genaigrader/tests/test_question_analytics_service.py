from django.contrib.auth.models import User
from django.test import TestCase

from genaigrader.models import (
    Course,
    Evaluation,
    Exam,
    Model,
    Question,
    QuestionEvaluation,
    QuestionOption,
)
from genaigrader.services.question_analytics_service import calculate_question_analytics


class QuestionAnalyticsServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="analytics_user", password="secret"
        )
        self.course = Course.objects.create(name="Course", user=self.user)
        self.exam = Exam.objects.create(
            course=self.course, description="Exam", user=self.user
        )

        self.question = Question.objects.create(
            statement="What is correct?", exam=self.exam
        )
        self.option_a = QuestionOption.objects.create(
            question=self.question, content="a) Correct"
        )
        self.option_b = QuestionOption.objects.create(
            question=self.question, content="b) Wrong"
        )
        self.question.correct_option = self.option_a
        self.question.save()

        self.model = Model.objects.create(description="test-model:1b")

    def _create_evaluation(self, grade, ev_time):
        return Evaluation.objects.create(
            prompt="prompt",
            ev_date="2026-01-01T00:00:00Z",
            grade=grade,
            time=ev_time,
            model=self.model,
            exam=self.exam,
        )

    def test_calculate_question_analytics_handles_null_question_option(self):
        eval_correct = self._create_evaluation(10, 1.5)
        eval_invalid = self._create_evaluation(0, 1.8)

        QuestionEvaluation.objects.create(
            evaluation=eval_correct,
            question=self.question,
            question_option=self.option_a,
        )
        QuestionEvaluation.objects.create(
            evaluation=eval_invalid,
            question=self.question,
            question_option=None,
        )

        stats = calculate_question_analytics(self.question)

        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["model_name"], self.model.description)
        self.assertEqual(stats[0]["total_evaluations"], 2)
        self.assertEqual(stats[0]["invalid_evaluations"], 1)
        self.assertEqual(stats[0]["accuracy"], 50.0)

    def test_question_evaluation_str_handles_null_option(self):
        evaluation = self._create_evaluation(0, 2.0)
        question_evaluation = QuestionEvaluation.objects.create(
            evaluation=evaluation,
            question=self.question,
            question_option=None,
        )

        self.assertIn("Option None", str(question_evaluation))
