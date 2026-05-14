from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from genaigrader.models import Course, Evaluation, Exam, Model, Question, QuestionOption
from genaigrader.services.stream_service import (
    create_evaluation_stub,
    evaluate_single_question,
)

User = get_user_model()


class NotesFunctionalityTest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.exam = Exam.objects.create(
            course=self.course, description="Test Exam", user=self.user
        )
        self.model = Model.objects.create(description="Test Model")

        self.question = Question.objects.create(
            statement="What is 2+2?", exam=self.exam
        )
        self.option_a = QuestionOption.objects.create(
            content="a) 3", question=self.question
        )
        self.option_b = QuestionOption.objects.create(
            content="b) 4", question=self.question
        )
        self.question.correct_option = self.option_b
        self.question.save()

    def test_evaluation_model_has_notes_field(self):
        """Test that the Evaluation model has a notes field with correct properties"""
        test_notes = "This exam was conducted on high-performance hardware"
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.model,
            exam=self.exam,
            notes=test_notes,
        )

        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertEqual(saved_evaluation.notes, test_notes)

    def test_evaluation_notes_field_can_be_null(self):
        """Test that the notes field can be null/empty"""
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.model,
            exam=self.exam,
            notes=None,
        )

        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertIsNone(saved_evaluation.notes)

    @patch("genaigrader.services.stream_service.generate_prompt")
    @patch("genaigrader.services.stream_service.get_evaluation_ollama_version")
    def test_create_evaluation_stub_preserves_notes(
        self, mock_ollama_version, mock_generate_prompt
    ):
        """Test that create_evaluation_stub correctly stores the notes parameter"""
        mock_ollama_version.return_value = "1.0.0"
        mock_generate_prompt.return_value = {
            "prompt": "Test prompt",
            "question_prompt": "What is 2+2?",
            "user_prompt": "Test user prompt",
        }

        test_notes = "Hardware: AMD Ryzen 9, 32GB RAM"
        evaluation = create_evaluation_stub(
            self.exam.id, self.model.id, user_prompt="Test prompt", notes=test_notes
        )

        self.assertEqual(evaluation.notes, test_notes)

    @patch("genaigrader.services.stream_service.generate_prompt")
    @patch("genaigrader.services.stream_service.get_evaluation_ollama_version")
    def test_evaluate_single_question_preserves_notes(
        self, mock_ollama_version, mock_generate_prompt
    ):
        """Test that evaluation notes are preserved through the full question flow"""
        mock_ollama_version.return_value = "1.0.0"
        mock_generate_prompt.return_value = {
            "prompt": "Test prompt",
            "question_prompt": "What is 2+2?",
            "user_prompt": "Test user prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["b"]

        test_notes = "Hardware: AMD Ryzen 9, 32GB RAM"
        evaluation = create_evaluation_stub(
            self.exam.id, self.model.id, user_prompt="Test prompt", notes=test_notes
        )

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            evaluate_single_question(evaluation.id, self.question.id, "Test prompt")

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.status, "completed")
        self.assertEqual(evaluation.notes, test_notes)

    @patch("genaigrader.services.stream_service.generate_prompt")
    @patch("genaigrader.services.stream_service.get_evaluation_ollama_version")
    def test_evaluate_single_question_works_without_notes(
        self, mock_ollama_version, mock_generate_prompt
    ):
        """Test that evaluation works correctly when no notes are provided"""
        mock_ollama_version.return_value = "1.0.0"
        mock_generate_prompt.return_value = {
            "prompt": "Test prompt",
            "question_prompt": "What is 2+2?",
            "user_prompt": "Test user prompt",
        }

        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ["b"]

        evaluation = create_evaluation_stub(
            self.exam.id, self.model.id, user_prompt="Test prompt"
        )

        with patch("genaigrader.services.stream_service.LlmApi", return_value=mock_llm):
            evaluate_single_question(evaluation.id, self.question.id, "Test prompt")

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.status, "completed")
        self.assertIsNone(evaluation.notes)
