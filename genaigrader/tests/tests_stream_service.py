import json
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from genaigrader.models import Course, Evaluation, Exam, Model, QuestionEvaluation

from ..services.stream_service import process_question, stream_responses


class StreamServiceTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.login(username="testuser", password="password")

        # Create related data
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.model = Model.objects.create(description="Test Model")
        self.exam = Exam.objects.create(
            course=self.course, description="Test Exam", user=self.user
        )

    @patch("genaigrader.services.stream_service.QuestionEvaluation")
    def test_stream_responses_handles_api_error(self, mock_question_evaluation):
        """
        Test that when an external model API call fails, stream_responses
        yields a data object containing an error message for batch_evaluations.js
        """
        # Setup mock QuestionEvaluation to avoid Django validation errors
        mock_question_evaluation_instance = Mock()
        mock_question_evaluation.objects.create.return_value = (
            mock_question_evaluation_instance
        )

        # Setup
        mock_question = Mock()
        mock_question.id = 1
        mock_question.statement = "Test question"
        mock_question.correct_option.content = "a"
        mock_questions = [mock_question]

        # Create a mock for the questionoption_set
        mock_options_queryset = MagicMock()
        mock_options_queryset.all.return_value.order_by.return_value = (
            []
        )  # Empty iterable
        mock_question.questionoption_set = mock_options_queryset

        mock_user_prompt = "test prompt"

        # Create mock LLM that will throw an Exception when generate_response is called
        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.side_effect = Exception("API call failed")

        mock_total_questions = 1
        mock_exam = self.exam

        # Execute
        response_generator = stream_responses(
            mock_questions, mock_user_prompt, mock_llm, mock_total_questions, mock_exam
        )
        responses = list(response_generator)  # Consume the generator

        # We should have exactly one response with an error
        self.assertEqual(
            len(responses), 1, "Expected exactly one response containing an error"
        )

        # Parse the response to check for the error
        response = responses[0]
        self.assertTrue(
            response.startswith("data: "), "Response should start with 'data: '"
        )

        data = json.loads(response[6:].strip())  # Skip the "data: " prefix

        # Verify error data
        self.assertIn("error", data, "Response should contain an error field")
        self.assertIn("API call failed", data["error"])
        self.assertEqual(data["processed_questions"], 1)
        self.assertEqual(data["total_questions"], mock_total_questions)
        self.assertEqual(data["correct_count"], 0)

        # Verify that no Evaluation or Questions were added to the database
        self.assertEqual(
            Evaluation.objects.count(),
            0,
            "No Evaluation should be created when an error occurs",
        )
        self.assertEqual(
            QuestionEvaluation.objects.count(),
            0,
            "No Questions should be created when an error occurs",
        )

    @patch("genaigrader.services.stream_service.QuestionEvaluation")
    @patch("genaigrader.services.stream_service.generate_prompt")
    def test_process_question_handles_api_error(
        self, mock_generate_prompt, mock_question_evaluation
    ):
        """
        Test that when the LlmApi raises an exception, process_question propagates the exception
        and no QuestionEvaluation is created
        """
        # Setup for generate_prompt mock
        mock_prompt_data = {
            "question_prompt": "Test question",
            "user_prompt": "Test user prompt",
            "prompt": "Full test prompt",
        }
        mock_generate_prompt.return_value = mock_prompt_data

        # Setup for question
        mock_question = Mock()
        mock_question.id = 1
        mock_question.statement = "Test question"
        mock_question.correct_option.content = "a"

        # Create a mock for questionoption_set
        mock_options_queryset = MagicMock()
        mock_options_queryset.all.return_value.order_by.return_value = []
        mock_question.questionoption_set = mock_options_queryset

        # Create mock LLM that will throw an Exception when generate_response is called
        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.side_effect = Exception("API call failed")

        question_evaluations = []

        # Execute and assert that the exception is propagated
        with self.assertRaises(Exception) as context:
            process_question(
                correct_count=0,
                index=0,
                question=mock_question,
                user_prompt="Test prompt",
                llm=mock_llm,
                total_questions=1,
                evaluation=Mock(),
                question_evaluations=question_evaluations,
            )

        # Verify the exception message
        self.assertEqual(str(context.exception), "API call failed")

        # Verify that no QuestionEvaluation was created
        mock_question_evaluation.assert_not_called()

        # Verify that question_evaluations list remains empty
        self.assertEqual(len(question_evaluations), 0)
