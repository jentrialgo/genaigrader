from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
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
from genaigrader.services.stream_service import (
    compute_evaluation_summary,
    create_evaluation_stub,
    evaluate_single_question,
)

User = get_user_model()


def _create_exam_with_questions(user, course, model, num_questions=1):
    exam = Exam.objects.create(course=course, description="Test Exam", user=user)
    questions = []
    for i in range(num_questions):
        question = Question.objects.create(statement=f"What is {i}+{i}?", exam=exam)
        option_a = QuestionOption.objects.create(content=f"a) {i}", question=question)
        option_b = QuestionOption.objects.create(
            content=f"b) {i + i}", question=question
        )
        question.correct_option = option_b
        question.save()
        questions.append((question, option_a, option_b))
    return exam, questions


class CreateEvaluationStubTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.model = Model.objects.create(description="Test Model")

    @patch("genaigrader.services.ollama_version_service.get_ollama_version")
    def test_create_evaluation_stub_success(self, mock_ollama_version):
        mock_ollama_version.return_value = None
        exam, _ = _create_exam_with_questions(
            self.user, self.course, self.model, num_questions=3
        )

        evaluation = create_evaluation_stub(
            exam.id, self.model.id, user_prompt="Custom prompt", notes="test notes"
        )

        self.assertEqual(evaluation.exam, exam)
        self.assertEqual(evaluation.model, self.model)
        self.assertEqual(evaluation.status, "pending")
        self.assertEqual(evaluation.total_questions, 3)
        self.assertIn("Custom prompt", evaluation.prompt)
        self.assertEqual(evaluation.notes, "test notes")

    def test_create_evaluation_stub_no_questions_raises(self):
        exam = Exam.objects.create(
            course=self.course, description="Empty Exam", user=self.user
        )

        with self.assertRaises(ValueError) as cm:
            create_evaluation_stub(exam.id, self.model.id)

        self.assertIn("has no questions", str(cm.exception))


class ComputeEvaluationSummaryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.model = Model.objects.create(description="Test Model")
        self.exam, self.questions = _create_exam_with_questions(
            self.user, self.course, self.model, num_questions=2
        )

    def test_compute_evaluation_summary_all_correct(self):
        from django.utils import timezone

        evaluation = Evaluation.objects.create(
            prompt="test",
            ev_date=timezone.now(),
            grade=0,
            time=0,
            model=self.model,
            exam=self.exam,
        )
        for q, _, opt_b in self.questions:
            QuestionEvaluation.objects.create(
                evaluation=evaluation,
                question=q,
                question_option=opt_b,
                is_correct=True,
            )

        grade, total_time = compute_evaluation_summary(evaluation)
        self.assertEqual(grade, 10.0)
        self.assertGreaterEqual(total_time, 0)

    def test_compute_evaluation_summary_half_correct(self):
        from django.utils import timezone

        evaluation = Evaluation.objects.create(
            prompt="test",
            ev_date=timezone.now(),
            grade=0,
            time=0,
            model=self.model,
            exam=self.exam,
        )
        q0, opt_a0, opt_b0 = self.questions[0]
        q1, _, opt_b1 = self.questions[1]
        QuestionEvaluation.objects.create(
            evaluation=evaluation,
            question=q0,
            question_option=opt_a0,
            is_correct=False,
        )
        QuestionEvaluation.objects.create(
            evaluation=evaluation,
            question=q1,
            question_option=opt_b1,
            is_correct=True,
        )

        grade, total_time = compute_evaluation_summary(evaluation)
        self.assertEqual(grade, 5.0)

    def test_compute_evaluation_summary_no_question_evaluations(self):
        from django.utils import timezone

        evaluation = Evaluation.objects.create(
            prompt="test",
            ev_date=timezone.now(),
            grade=0,
            time=0,
            model=self.model,
            exam=self.exam,
        )

        grade, total_time = compute_evaluation_summary(evaluation)
        self.assertEqual(grade, 0.0)
        self.assertEqual(total_time, 0.0)


class EvaluateSingleQuestionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.model = Model.objects.create(description="Test Model")
        self.exam, self.questions = _create_exam_with_questions(
            self.user, self.course, self.model, num_questions=1
        )
        self.question, self.option_a, self.option_b = self.questions[0]
        from django.utils import timezone

        self.evaluation = Evaluation.objects.create(
            prompt="test",
            ev_date=timezone.now(),
            grade=0,
            time=0,
            model=self.model,
            exam=self.exam,
            status="pending",
            total_questions=1,
        )

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_correct_answer(self, mock_generate_prompt):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["b) 0"]

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            result = evaluate_single_question(
                self.evaluation.id, self.question.id, "Test prompt"
            )

        self.assertTrue(result["is_correct"])
        self.assertEqual(result["response"], "b")
        self.assertTrue(result["evaluation_complete"])
        self.assertEqual(result["grade"], 10.0)

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "completed")
        self.assertEqual(self.evaluation.grade, 10.0)

        qe = QuestionEvaluation.objects.filter(evaluation=self.evaluation).first()
        self.assertEqual(qe.question_option, self.option_b)
        self.assertEqual(qe.response_text, "b")

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_incorrect_answer(self, mock_generate_prompt):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["a) 0"]

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            result = evaluate_single_question(
                self.evaluation.id, self.question.id, "Test prompt"
            )

        self.assertFalse(result["is_correct"])
        self.assertEqual(result["response"], "a")
        self.assertTrue(result["evaluation_complete"])

        qe = QuestionEvaluation.objects.filter(evaluation=self.evaluation).first()
        self.assertEqual(qe.response_text, "a")

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "completed")
        self.assertEqual(self.evaluation.grade, 0.0)

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_empty_llm_response(self, mock_generate_prompt):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = []

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            result = evaluate_single_question(
                self.evaluation.id, self.question.id, "Test prompt"
            )

        self.assertEqual(result["response"], "")
        self.assertFalse(result["is_correct"])
        self.assertTrue(result["evaluation_complete"])

        qe = QuestionEvaluation.objects.filter(evaluation=self.evaluation).first()
        self.assertEqual(qe.response_text, "")

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_api_error_marks_failed(
        self, mock_generate_prompt
    ):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.side_effect = RuntimeError("API call failed")

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            with self.assertRaises(RuntimeError) as context:
                evaluate_single_question(
                    self.evaluation.id, self.question.id, "Test prompt"
                )

        self.assertEqual(str(context.exception), "API call failed")

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "failed")
        self.assertEqual(self.evaluation.failed_question_id, self.question.id)
        self.assertIn("API call failed", self.evaluation.failed_reason)

        self.assertEqual(
            QuestionEvaluation.objects.filter(evaluation=self.evaluation).count(), 0
        )

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_generic_exception_marks_failed(
        self, mock_generate_prompt
    ):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        class ReadTimeout(Exception):
            pass

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.side_effect = ReadTimeout("timed out after 300s")

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            with self.assertRaises(ReadTimeout):
                evaluate_single_question(
                    self.evaluation.id, self.question.id, "Test prompt"
                )

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "failed")
        self.assertEqual(self.evaluation.failed_question_id, self.question.id)
        self.assertIn("ReadTimeout", self.evaluation.failed_reason)
        self.assertIn("timed out after 300s", self.evaluation.failed_reason)

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_failed_reason_truncated(
        self, mock_generate_prompt
    ):
        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        long_message = "x" * 1000
        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.side_effect = RuntimeError(long_message)

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            with self.assertRaises(RuntimeError):
                evaluate_single_question(
                    self.evaluation.id, self.question.id, "Test prompt"
                )

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "failed")
        self.assertLessEqual(len(self.evaluation.failed_reason), 500)

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_does_not_aggregate_when_not_last(
        self, mock_generate_prompt
    ):
        # Create a second question so this evaluation has 2 total questions
        q2 = Question.objects.create(statement="What is 1+1?", exam=self.exam)
        QuestionOption.objects.create(content="a) 1", question=q2)
        opt_b2 = QuestionOption.objects.create(content="b) 2", question=q2)
        q2.correct_option = opt_b2
        q2.save()

        self.evaluation.total_questions = 2
        self.evaluation.save()

        mock_generate_prompt.return_value = {
            "question_prompt": "What is 0+0?",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["b) 0"]

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            result = evaluate_single_question(
                self.evaluation.id, self.question.id, "Test prompt"
            )

        self.assertFalse(result["evaluation_complete"])
        self.assertIsNone(result["grade"])

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "running")

    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_evaluate_single_question_race_condition_safe(self, mock_generate_prompt):
        """Simulate two tasks finishing concurrently; only one should aggregate."""
        q2 = Question.objects.create(statement="What is 1+1?", exam=self.exam)
        QuestionOption.objects.create(content="a) 1", question=q2)
        opt_b2 = QuestionOption.objects.create(content="b) 2", question=q2)
        q2.correct_option = opt_b2
        q2.save()

        self.evaluation.total_questions = 2
        self.evaluation.save()

        mock_generate_prompt.return_value = {
            "question_prompt": "Test",
            "user_prompt": "Test prompt",
            "prompt": "Full test prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["b) 0"]

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            result1 = evaluate_single_question(
                self.evaluation.id, self.question.id, "Test prompt"
            )
            result2 = evaluate_single_question(self.evaluation.id, q2.id, "Test prompt")

        # Exactly one of them should have triggered completion
        self.assertTrue(
            result1["evaluation_complete"] or result2["evaluation_complete"]
        )
        self.assertFalse(
            result1["evaluation_complete"] and result2["evaluation_complete"]
        )

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.status, "completed")
        self.assertEqual(self.evaluation.grade, 10.0)
