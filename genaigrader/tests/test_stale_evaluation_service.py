from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_q.models import OrmQ
from django_q.signing import SignedPackage

from genaigrader.models import (
    Course,
    Evaluation,
    Exam,
    Model,
    Question,
    QuestionEvaluation,
    QuestionOption,
)
from genaigrader.services.stale_evaluation_service import reap_stale_evaluations

User = get_user_model()


def _make_ormq_payload(func_path, args=None, kwargs=None, task_id="a" * 32):
    return SignedPackage.dumps(
        {
            "id": task_id,
            "func": func_path,
            "args": args or (),
            "kwargs": kwargs or {},
            "name": func_path.rsplit(".", 1)[-1],
        }
    )


class ReapStaleEvaluationsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password"
        )
        self.course = Course.objects.create(name="Test Course", user=self.user)
        self.model = Model.objects.create(description="Test Model")
        self.exam = Exam.objects.create(
            course=self.course, description="Test Exam", user=self.user
        )
        self.question = Question.objects.create(
            statement="What is 2+2?", exam=self.exam
        )
        QuestionOption.objects.create(content="a) 3", question=self.question)
        option_b = QuestionOption.objects.create(content="b) 4", question=self.question)
        self.question.correct_option = option_b
        self.question.save()

    def _create_evaluation(self, status="running", total_questions=2, age_hours=2):
        ev = Evaluation.objects.create(
            prompt="test",
            ev_date=timezone.now() - timedelta(hours=age_hours),
            grade=0,
            time=0,
            model=self.model,
            exam=self.exam,
            status=status,
            total_questions=total_questions,
        )
        return ev

    def test_stale_running_no_queue_marks_failed(self):
        ev = self._create_evaluation(status="running", total_questions=2)
        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "failed")
        self.assertIn("Stale", ev.failed_reason)
        self.assertIn("0/2", ev.failed_reason)
        self.assertEqual(result["reaped"], 1)
        self.assertIn(ev.id, result["reaped_ids"])

    def test_stale_pending_no_queue_marks_failed(self):
        ev = self._create_evaluation(status="pending", total_questions=2)
        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "failed")
        self.assertEqual(result["reaped"], 1)

    def test_recent_evaluation_not_reaped(self):
        ev = self._create_evaluation(status="running", total_questions=2, age_hours=0.1)
        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "running")
        self.assertEqual(result["reaped"], 0)

    def test_evaluation_with_queue_tasks_not_reaped(self):
        ev = self._create_evaluation(status="running", total_questions=2)
        OrmQ.objects.create(
            key="test-key-stale",
            payload=_make_ormq_payload(
                "genaigrader.tasks.evaluate_question_task", args=[ev.id]
            ),
        )

        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "running")
        self.assertEqual(result["reaped"], 0)

    def test_completed_evaluation_not_reaped(self):
        ev = self._create_evaluation(status="completed", total_questions=2)
        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "completed")
        self.assertEqual(result["reaped"], 0)

    def test_failed_evaluation_not_reaped(self):
        ev = self._create_evaluation(status="failed", total_questions=2)
        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "failed")
        self.assertEqual(result["reaped"], 0)

    def test_all_questions_done_marks_completed(self):
        """If all QuestionEvaluations exist but status is stuck, fix to completed."""
        ev = self._create_evaluation(status="running", total_questions=1)
        QuestionEvaluation.objects.create(
            evaluation=ev,
            question=self.question,
            question_option=self.question.correct_option,
            is_correct=True,
            question_time=1.0,
        )

        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "completed")
        self.assertEqual(ev.grade, 10.0)
        self.assertEqual(result["reaped"], 0)

    def test_partial_questions_marks_failed(self):
        """Some questions done but not all, no queue → failed."""
        ev = self._create_evaluation(status="running", total_questions=2)
        QuestionEvaluation.objects.create(
            evaluation=ev,
            question=self.question,
            question_option=self.question.correct_option,
            is_correct=True,
            question_time=1.0,
        )

        result = reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "failed")
        self.assertIn("1/2", ev.failed_reason)
        self.assertEqual(result["reaped"], 1)

    def test_grace_period_override(self):
        ev = self._create_evaluation(status="running", total_questions=2, age_hours=0.1)
        result = reap_stale_evaluations(grace_minutes=1)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "failed")
        self.assertEqual(result["reaped"], 1)

    def test_failed_reason_truncated(self):
        """Failed reason should not exceed 500 chars."""
        ev = self._create_evaluation(status="running", total_questions=999999)
        reap_stale_evaluations(grace_minutes=30)

        ev.refresh_from_db()
        self.assertLessEqual(len(ev.failed_reason), 500)
