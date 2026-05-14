from datetime import datetime, timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone as django_tz

from genaigrader.models import Course, Evaluation, Exam, Model

User = get_user_model()


def _make_eval_for_user(user, description="Test Exam"):
    """Create a minimal evaluation the user owns."""
    course = Course.objects.create(name="Test Course", user=user)
    exam = Exam.objects.create(course=course, description=description, user=user)
    model = Model.objects.create(description="Test Model")
    return Evaluation.objects.create(
        prompt="test",
        ev_date=django_tz.now(),
        grade=0,
        time=0,
        model=model,
        exam=exam,
        status="pending",
        total_questions=1,
    )


class TaskStatusViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.client.force_login(self.user)

    def test_task_status_requires_login(self):
        client = Client()
        response = client.get("/task/some-task-id/")
        self.assertEqual(response.status_code, 302)

    @patch("genaigrader.views.task_views.Task")
    def test_task_status_queued(self, mock_task_class):
        mock_task_class.objects.filter.return_value.first.return_value = None

        response = self.client.get("/task/queued-task-id/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["task_id"], "queued-task-id")

    @patch("genaigrader.views.task_views.Task")
    def test_task_status_success(self, mock_task_class):
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_task.name = "pull_model"
        mock_task.success = True
        mock_task.started = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_task.stopped = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        mock_task.result = {"model_id": 1, "status": "downloaded"}
        mock_task.group = None

        mock_task_class.objects.filter.return_value.first.return_value = mock_task

        response = self.client.get("/task/test-task-id/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["task_id"], "test-task-id")
        self.assertEqual(data["name"], "pull_model")
        self.assertEqual(data["result"]["status"], "downloaded")

    @patch("genaigrader.views.task_views.Task")
    def test_task_status_failed(self, mock_task_class):
        mock_task = Mock()
        mock_task.id = "failed-task-id"
        mock_task.name = "evaluate_question_task"
        mock_task.success = False
        mock_task.started = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_task.stopped = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        mock_task.result = Exception("Evaluation error")
        mock_task.group = None

        mock_task_class.objects.filter.return_value.first.return_value = mock_task

        response = self.client.get("/task/failed-task-id/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["result"], "Evaluation error")

    @patch("genaigrader.views.task_views.Task")
    def test_task_status_evaluation_forbidden(self, mock_task_class):
        """A task whose group points to another user's evaluation is 403."""
        other_user = User.objects.create_user(
            username="other", email="other@example.com", password="password"
        )
        evaluation = _make_eval_for_user(other_user)

        mock_task = Mock()
        mock_task.id = "forbidden-task-id"
        mock_task.name = "evaluate_question_task"
        mock_task.success = True
        mock_task.started = None
        mock_task.stopped = None
        mock_task.result = {"evaluation_id": evaluation.id}
        mock_task.group = f"eval:{evaluation.id}"

        mock_task_class.objects.filter.return_value.first.return_value = mock_task

        response = self.client.get("/task/forbidden-task-id/")
        self.assertEqual(response.status_code, 403)

    @patch("genaigrader.views.task_views.Task")
    def test_task_status_evaluation_authorized(self, mock_task_class):
        """A task whose group points to the current user's evaluation is OK."""
        evaluation = _make_eval_for_user(self.user)

        mock_task = Mock()
        mock_task.id = "authorized-task-id"
        mock_task.name = "evaluate_question_task"
        mock_task.success = True
        mock_task.started = None
        mock_task.stopped = None
        mock_task.result = {"evaluation_id": evaluation.id}
        mock_task.group = f"eval:{evaluation.id}"

        mock_task_class.objects.filter.return_value.first.return_value = mock_task

        response = self.client.get("/task/authorized-task-id/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["result"]["evaluation_id"], evaluation.id)

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_missing_ids(self, mock_task_class):
        response = self.client.get("/batch-task-status/")
        self.assertEqual(response.status_code, 400)

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_all_queued(self, mock_task_class):
        mock_task_class.objects.filter.return_value.in_bulk.return_value = {}

        response = self.client.get("/batch-task-status/?ids=id1,id2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], 0)
        self.assertEqual(data["pending"], 2)
        self.assertEqual(data["total"], 2)
        for r in data["results"]:
            self.assertEqual(r["status"], "queued")

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_single_success(self, mock_task_class):
        mock_task = Mock()
        mock_task.id = "done-task-id"
        mock_task.name = "evaluate_question_task"
        mock_task.success = True
        mock_task.started = None
        mock_task.stopped = None
        mock_task.result = {"evaluation_id": 1, "grade": 8.5}
        mock_task.group = None

        mock_task_class.objects.filter.return_value.in_bulk.return_value = {
            "done-task-id": mock_task,
        }

        response = self.client.get(
            "/batch-task-status/?ids=done-task-id,missing-task-id"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], 1)
        self.assertEqual(data["pending"], 1)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["results"][0]["status"], "success")
        self.assertEqual(data["results"][0]["task_id"], "done-task-id")
        self.assertEqual(data["results"][1]["status"], "queued")
        self.assertEqual(data["results"][1]["task_id"], "missing-task-id")

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_forbidden_counts_as_finished(self, mock_task_class):
        other_user = User.objects.create_user(
            username="other-batch", email="other-batch@example.com", password="password"
        )
        evaluation = _make_eval_for_user(other_user)

        mock_task = Mock()
        mock_task.id = "forbidden-task-id"
        mock_task.name = "evaluate_question_task"
        mock_task.success = True
        mock_task.started = None
        mock_task.stopped = None
        mock_task.result = {"evaluation_id": evaluation.id}
        mock_task.group = f"eval:{evaluation.id}"

        mock_task_class.objects.filter.return_value.in_bulk.return_value = {
            "forbidden-task-id": mock_task,
        }

        response = self.client.get("/batch-task-status/?ids=forbidden-task-id")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], 1)
        self.assertEqual(data["pending"], 0)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["status"], "forbidden")

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_processing_count(self, mock_task_class):
        mock_task_class.objects.filter.return_value.in_bulk.return_value = {}

        response = self.client.get("/batch-task-status/?ids=id1,id2,id3")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], 0)
        self.assertEqual(data["pending"], 3)
        self.assertEqual(data["total"], 3)
        for r in data["results"]:
            self.assertEqual(r["status"], "queued")

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_post_with_list_body(self, mock_task_class):
        """POST with a JSON list body is accepted and equivalent to GET."""
        mock_task_class.objects.filter.return_value.in_bulk.return_value = {}

        response = self.client.post(
            "/batch-task-status/",
            data='{"ids": ["id1","id2"]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], 0)
        self.assertEqual(data["pending"], 2)
        self.assertEqual(data["total"], 2)

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_post_with_comma_string_body(self, mock_task_class):
        """POST with a comma-separated string body is also accepted."""
        mock_task_class.objects.filter.return_value.in_bulk.return_value = {}

        response = self.client.post(
            "/batch-task-status/",
            data='{"ids": "id1,id2,id3"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["pending"], 3)

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_post_invalid_json(self, mock_task_class):
        """Invalid JSON body returns 400 instead of 500."""
        response = self.client.post(
            "/batch-task-status/",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("genaigrader.views.task_views.Task")
    def test_batch_task_status_post_missing_ids_key(self, mock_task_class):
        """JSON without 'ids' key returns 400."""
        response = self.client.post(
            "/batch-task-status/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
