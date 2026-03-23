import unittest
from unittest.mock import Mock, patch

from genaigrader.views.batch_evaluations_view import (
    extract_summary,
    validate_exam,
    validate_model,
)


class ValidateExamTestCase(unittest.TestCase):

    def test_validate_exam_with_questions(self):
        """Should not raise an error if the exam has at least one question."""
        mock_exam = Mock()
        mock_questions = Mock()
        mock_questions.exists.return_value = True
        mock_exam.question_set.prefetch_related.return_value.all.return_value = (
            mock_questions
        )

        try:
            validate_exam(mock_exam)  # Should not raise
        except ValueError:
            self.fail("validate_exam() raised ValueError unexpectedly!")

    def test_validate_exam_without_questions(self):
        """Should raise ValueError if the exam has no questions."""
        mock_exam = Mock()
        mock_questions = Mock()
        mock_questions.exists.return_value = False
        mock_exam.question_set.prefetch_related.return_value.all.return_value = (
            mock_questions
        )

        with self.assertRaises(ValueError):
            validate_exam(mock_exam)


class ValidateModelTestCase(unittest.TestCase):

    @patch("genaigrader.views.batch_evaluations_view.LlmApi")
    def test_validate_model_success(self, mock_llmapi_class):
        """Should return a valid LlmApi instance when validation passes."""
        mock_llm = Mock()
        mock_llm.validate.return_value = None
        mock_llmapi_class.return_value = mock_llm

        model = Mock()
        result = validate_model(model)
        self.assertEqual(result, mock_llm)

    @patch("genaigrader.views.batch_evaluations_view.LlmApi")
    def test_validate_model_failure(self, mock_llmapi_class):
        """Should raise ValueError when model validation fails."""
        mock_llm = Mock()
        mock_llm.validate.side_effect = ValueError("invalid model")
        mock_llmapi_class.return_value = mock_llm

        model = Mock()
        with self.assertRaises(ValueError):
            validate_model(model)


class ExtractSummaryTestCase(unittest.TestCase):

    def test_extract_summary_valid(self):
        """Should extract correct_count, total_time, and total_questions from a valid response."""
        responses = [
            'data: {"some": "value"}\n\n',
            'data: {"total_time": 3.14, "correct_count": 4, "total_questions": 5}\n\n',
        ]
        result = extract_summary(responses)
        correct_summary = {"grade": "8.0 (4/5)", "time": 3.14}
        self.assertEqual(result, correct_summary)

    def test_extract_summary_invalid_json(self):
        """Should return None if a response is not valid JSON."""
        responses = ["data: not a json string\n\n"]
        result = extract_summary(responses)
        self.assertIsNone(result)

    def test_extract_summary_no_relevant_data(self):
        """Should return None if no response contains the required keys."""
        responses = ['data: {"foo": "bar"}\n\n']
        result = extract_summary(responses)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
