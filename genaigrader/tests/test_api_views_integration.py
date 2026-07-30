import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from genaigrader.models import Course, Exam, Model, Question, QuestionOption

User = get_user_model()


class PullModelViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.client.force_login(self.user)

    @patch("genaigrader.views.api_views.async_task")
    def test_pull_model_queues_task(self, mock_async_task):
        mock_async_task.return_value = "fake-task-id"

        response = self.client.post(
            "/model/pull/",
            data=json.dumps({"model": "llama3.2:1b"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["task_id"], "fake-task-id")
        self.assertIn("llama3.2:1b", data["message"])

        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        from genaigrader.tasks import download_model_task

        self.assertEqual(call_args[0][0], download_model_task)
        self.assertEqual(call_args[0][1], "llama3.2:1b")
        self.assertEqual(call_args[1]["timeout"], 7200)

    def test_pull_model_empty_name(self):
        response = self.client.post(
            "/model/pull/",
            data=json.dumps({"model": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("cannot be empty", data["message"])

    def test_pull_model_already_exists(self):
        Model.objects.create(description="llama3.2:1b")

        response = self.client.post(
            "/model/pull/",
            data=json.dumps({"model": "llama3.2:1b"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("already exists", data["message"])

    def test_pull_model_get_not_allowed(self):
        response = self.client.get("/model/pull/")

        self.assertEqual(response.status_code, 405)

    @patch("genaigrader.views.api_views.async_task")
    def test_pull_model_strips_whitespace(self, mock_async_task):
        mock_async_task.return_value = "fake-task-id"

        response = self.client.post(
            "/model/pull/",
            data=json.dumps({"model": "  llama3.2:1b  "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][1], "llama3.2:1b")

    def test_pull_model_requires_login(self):
        """Unauthenticated users must be redirected to login."""
        client = Client()
        response = client.post(
            "/model/pull/",
            data=json.dumps({"model": "test-unauthenticated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)


class BatchEvaluationsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.client.force_login(self.user)
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.exam = Exam.objects.create(
            course=self.course, description="Test Exam", user=self.user
        )
        self.model = Model.objects.create(description="Test Model")
        # Each exam must have at least one question for create_evaluation_stub
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

    @patch("genaigrader.services.ollama_version_service.get_ollama_version")
    @patch("genaigrader.views.batch_evaluations_view.async_task")
    def test_batch_evaluation_queues_per_question_tasks(
        self, mock_async_task, mock_ollama_version
    ):
        mock_async_task.return_value = "fake-task-id"
        mock_ollama_version.return_value = None

        response = self.client.post(
            "/batch-evaluations/",
            data=json.dumps(
                {
                    "exams[]": [str(self.exam.id)],
                    "models[]": [str(self.model.id)],
                    "repetitions": 1,
                    "user_prompt": "",
                    "notes": "",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["task_ids"], [])
        self.assertEqual(data["total_tasks"], 1)
        self.assertEqual(len(data["evaluation_ids"]), 1)

        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        from genaigrader.tasks import batch_orchestrator_task

        self.assertEqual(call_args[0][0], batch_orchestrator_task)

    @patch("genaigrader.services.ollama_version_service.get_ollama_version")
    @patch("genaigrader.views.batch_evaluations_view.async_task")
    def test_batch_evaluation_multiple_tasks_calculation(
        self, mock_async_task, mock_ollama_version
    ):
        exam2 = Exam.objects.create(
            course=self.course, description="Test Exam 2", user=self.user
        )
        q2 = Question.objects.create(statement="Q2?", exam=exam2)
        QuestionOption.objects.create(content="a) x", question=q2)
        opt_b2 = QuestionOption.objects.create(content="b) y", question=q2)
        q2.correct_option = opt_b2
        q2.save()

        mock_async_task.return_value = "fake-task-id"
        mock_ollama_version.return_value = None

        response = self.client.post(
            "/batch-evaluations/",
            data=json.dumps(
                {
                    "exams[]": [str(self.exam.id), str(exam2.id)],
                    "models[]": [str(self.model.id)],
                    "repetitions": 2,
                    "user_prompt": "test prompt",
                    "notes": "test notes",
                }
            ),
            content_type="application/json",
        )

        data = response.json()
        self.assertEqual(data["total_tasks"], 4)
        self.assertEqual(data["task_ids"], [])
        self.assertEqual(len(data["evaluation_ids"]), 4)

    def test_batch_evaluation_get_renders_template(self):
        response = self.client.get("/batch-evaluations/")

        self.assertEqual(response.status_code, 200)

    def test_batch_evaluation_requires_login(self):
        client = Client()
        response = client.get("/batch-evaluations/")
        self.assertEqual(response.status_code, 302)

    @patch("genaigrader.services.ollama_version_service.get_ollama_version")
    @patch("genaigrader.views.batch_evaluations_view.async_task")
    def test_batch_evaluation_ordered_by_model(
        self, mock_async_task, mock_ollama_version
    ):
        """Tasks must be enqueued grouped by model (model → exam → rep)."""
        exam2 = Exam.objects.create(
            course=self.course, description="Test Exam 2", user=self.user
        )
        q2 = Question.objects.create(statement="Q2?", exam=exam2)
        QuestionOption.objects.create(content="a) x", question=q2)
        opt_b2 = QuestionOption.objects.create(content="b) y", question=q2)
        q2.correct_option = opt_b2
        q2.save()

        model2 = Model.objects.create(description="Test Model 2")

        mock_async_task.return_value = "fake-task-id"
        mock_ollama_version.return_value = None

        response = self.client.post(
            "/batch-evaluations/",
            data=json.dumps(
                {
                    "exams[]": [str(self.exam.id), str(exam2.id)],
                    "models[]": [str(self.model.id), str(model2.id)],
                    "repetitions": 1,
                    "user_prompt": "",
                    "notes": "",
                }
            ),
            content_type="application/json",
        )

        data = response.json()
        self.assertEqual(data["total_tasks"], 4)

        # Evaluations meta must be ordered by model → exam (stubs created in that order)
        model_ids_in_order = [meta["model_id"] for meta in data["evaluations"]]
        seen_models = []
        for mid in model_ids_in_order:
            if not seen_models or seen_models[-1] != mid:
                seen_models.append(mid)
        self.assertEqual(
            len(seen_models),
            len(set(model_ids_in_order)),
            "Evaluations for the same model must be contiguous",
        )

    @patch("genaigrader.services.ollama_version_service.get_ollama_version")
    @patch("genaigrader.views.batch_evaluations_view.async_task")
    def test_batch_enqueue_interrupt_marks_failed(
        self, mock_async_task, mock_ollama_version
    ):
        """If orchestrator enqueue fails, created evaluations are marked failed."""
        mock_ollama_version.return_value = None
        # The view calls async_task once for the orchestrator; simulate failure
        mock_async_task.side_effect = RuntimeError("boom")

        self.client.raise_request_exception = False
        response = self.client.post(
            "/batch-evaluations/",
            data=json.dumps(
                {
                    "exams[]": [str(self.exam.id)],
                    "models[]": [str(self.model.id)],
                    "repetitions": 2,
                    "user_prompt": "",
                    "notes": "",
                }
            ),
            content_type="application/json",
        )

        # The exception should propagate as a 500
        self.assertEqual(response.status_code, 500)

        from genaigrader.models import Evaluation

        evals = Evaluation.objects.filter(exam=self.exam)
        self.assertEqual(evals.count(), 2)
        for ev in evals:
            self.assertEqual(ev.status, "failed")
            self.assertIn("Orchestrator", ev.failed_reason)
