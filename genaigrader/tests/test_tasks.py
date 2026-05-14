from unittest.mock import Mock, patch

from django.test import TestCase

from genaigrader.tasks import (
    download_model_task,
    evaluate_exam_task,
    evaluate_question_task,
)


def _mock_evaluation_exists():
    """Set up a mock so Evaluation.objects.filter(...).first() returns a mock evaluation."""
    mock_eval = Mock()
    mock_eval.status = "pending"
    mock_filter = Mock()
    mock_filter.first.return_value = mock_eval
    return patch(
        "genaigrader.tasks.Evaluation.objects.filter", return_value=mock_filter
    )


class EvaluateQuestionTaskTest(TestCase):
    @_mock_evaluation_exists()
    @patch("genaigrader.tasks.evaluate_single_question")
    def test_evaluate_question_task_calls_service(
        self, mock_evaluate_single_question, _mock_filter
    ):
        mock_evaluate_single_question.return_value = {
            "evaluation_id": 5,
            "question_id": 10,
            "response": "a",
            "is_correct": True,
            "question_time": 1.2,
            "evaluation_complete": False,
            "grade": None,
            "total_time": None,
        }

        result = evaluate_question_task(
            evaluation_id=5,
            question_id=10,
            user_prompt="test prompt",
        )

        mock_evaluate_single_question.assert_called_once_with(5, 10, "test prompt")
        self.assertEqual(result["evaluation_id"], 5)
        self.assertEqual(result["question_id"], 10)
        self.assertTrue(result["is_correct"])

    @_mock_evaluation_exists()
    @patch("genaigrader.tasks.evaluate_single_question")
    def test_evaluate_question_task_uses_defaults(
        self, mock_evaluate_single_question, _mock_filter
    ):
        mock_evaluate_single_question.return_value = {
            "evaluation_id": 1,
            "question_id": 2,
        }

        evaluate_question_task(evaluation_id=1, question_id=2)

        mock_evaluate_single_question.assert_called_once_with(1, 2, "")

    @_mock_evaluation_exists()
    @patch("genaigrader.tasks.evaluate_single_question")
    def test_evaluate_question_task_propagates_exception(
        self, mock_evaluate_single_question, _mock_filter
    ):
        mock_evaluate_single_question.side_effect = ValueError("Model not found")

        with self.assertRaises(ValueError) as cm:
            evaluate_question_task(evaluation_id=1, question_id=2)

        self.assertIn("Model not found", str(cm.exception))

    @patch("genaigrader.tasks.Evaluation.objects.filter")
    @patch("genaigrader.tasks.evaluate_single_question")
    def test_evaluate_question_task_discards_when_evaluation_deleted(
        self, mock_evaluate_single_question, mock_filter
    ):
        """Task should return discarded status when evaluation no longer exists."""
        mock_filter.return_value.first.return_value = None

        result = evaluate_question_task(evaluation_id=99, question_id=1)

        self.assertEqual(result["status"], "discarded")
        self.assertEqual(result["reason"], "evaluation deleted")
        mock_evaluate_single_question.assert_not_called()

    @patch("genaigrader.tasks.Evaluation.objects.filter")
    @patch("genaigrader.tasks.evaluate_single_question")
    def test_evaluate_question_task_discards_when_terminal(
        self, mock_evaluate_single_question, mock_filter
    ):
        """Task should return discarded status when evaluation is already terminal."""
        mock_eval = Mock()
        mock_eval.status = "completed"
        mock_filter.return_value.first.return_value = mock_eval

        result = evaluate_question_task(evaluation_id=99, question_id=1)

        self.assertEqual(result["status"], "discarded")
        self.assertEqual(result["reason"], "evaluation already completed")
        mock_evaluate_single_question.assert_not_called()


class DownloadModelTaskTest(TestCase):
    @patch("genaigrader.tasks.pull_model")
    def test_download_model_task_calls_service(self, mock_pull_model):
        mock_pull_model.return_value = {
            "model_id": 7,
            "model": "llama3.2:1b",
            "status": "downloaded",
        }

        result = download_model_task("llama3.2:1b")

        mock_pull_model.assert_called_once_with("llama3.2:1b")
        self.assertEqual(result["model_id"], 7)
        self.assertEqual(result["status"], "downloaded")

    @patch("genaigrader.tasks.pull_model")
    def test_download_model_task_propagates_exception(self, mock_pull_model):
        mock_pull_model.side_effect = RuntimeError("Download failed")

        with self.assertRaises(RuntimeError) as cm:
            download_model_task("unknown-model")

        self.assertIn("Download failed", str(cm.exception))


class EvaluateExamTaskTest(TestCase):
    def test_evaluate_exam_task_discards(self):
        """Legacy task wrapper returns discarded status regardless of args."""
        result = evaluate_exam_task(exam_id=1, model_id=2)
        self.assertEqual(result["status"], "discarded")
        self.assertEqual(result["reason"], "obsolete task name")

    def test_evaluate_exam_task_discards_with_kwargs(self):
        result = evaluate_exam_task(
            evaluation_id=5, exam_id=1, model_id=2, user_prompt="test"
        )
        self.assertEqual(result["status"], "discarded")
