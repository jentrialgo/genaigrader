from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone as django_tz

from genaigrader.models import (
    Course,
    Evaluation,
    Exam,
    Model,
    Question,
    QuestionEvaluation,
    QuestionOption,
)

User = get_user_model()


def _make_eval(user, status="pending", total=2, completed=0, grade=0.0, time=0.0):
    """Create a minimal evaluation owned by *user*.

    Optionally add ``completed`` QuestionEvaluation rows to simulate
    partial progress.
    """
    course = Course.objects.create(name="C-%s" % status, user=user)
    exam = Exam.objects.create(course=course, description="Exam-%s" % status, user=user)
    model = Model.objects.create(description="Model-%s" % status)
    evaluation = Evaluation.objects.create(
        prompt="prompt",
        ev_date=django_tz.now(),
        grade=grade,
        time=time,
        model=model,
        exam=exam,
        status=status,
        total_questions=total,
    )
    for i in range(completed):
        question = Question.objects.create(statement="Q%d" % i, exam=exam)
        option = QuestionOption.objects.create(content="a", question=question)
        question.correct_option = option
        question.save()
        QuestionEvaluation.objects.create(
            evaluation=evaluation,
            question=question,
            question_option=option,
            response_text="a",
            is_correct=True,
            question_time=0.1,
        )
    return evaluation


class EvaluationQuestionsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="u", email="u@example.com", password="pw"
        )
        self.client.force_login(self.user)

    def test_question_prompt_includes_all_options(self):
        course = Course.objects.create(name="C", user=self.user)
        exam = Exam.objects.create(course=course, description="E", user=self.user)
        model = Model.objects.create(description="M")
        evaluation = Evaluation.objects.create(
            prompt="prompt",
            ev_date=django_tz.now(),
            grade=0.0,
            time=0.0,
            model=model,
            exam=exam,
            status="completed",
            total_questions=1,
        )
        question = Question.objects.create(statement="What is 2+2?", exam=exam)
        QuestionOption.objects.create(content="a) 3", question=question)
        opt_b = QuestionOption.objects.create(content="b) 4", question=question)
        QuestionOption.objects.create(content="c) 5", question=question)
        question.correct_option = opt_b
        question.save()
        QuestionEvaluation.objects.create(
            evaluation=evaluation,
            question=question,
            question_option=opt_b,
            response_text="b",
            is_correct=True,
            question_time=0.1,
        )

        response = self.client.get(f"/evaluation/{evaluation.id}/questions/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions"]), 1)
        prompt = data["questions"][0]["question_prompt"]
        self.assertIn("What is 2+2?", prompt)
        self.assertIn("a) 3", prompt)
        self.assertIn("b) 4", prompt)
        self.assertIn("c) 5", prompt)


class BatchEvaluationStatusViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="u", email="u@example.com", password="pw"
        )
        self.client.force_login(self.user)

    def test_requires_login(self):
        client = Client()
        self.assertEqual(client.get("/batch-evaluation-status/?ids=1").status_code, 302)

    def test_get_missing_ids_returns_400(self):
        response = self.client.get("/batch-evaluation-status/")
        self.assertEqual(response.status_code, 400)

    def test_get_returns_status_in_input_order(self):
        ev_a = _make_eval(self.user, status="pending", total=2, completed=1)
        ev_b = _make_eval(self.user, status="completed", total=3, completed=3)

        # Request them in reverse order to verify the response preserves order.
        response = self.client.get(
            "/batch-evaluation-status/?ids=%d,%d" % (ev_b.id, ev_a.id)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["results"][0]["evaluation_id"], ev_b.id)
        self.assertEqual(data["results"][0]["status"], "completed")
        self.assertEqual(data["results"][0]["completed_tasks"], 3)
        self.assertEqual(data["results"][0]["total_tasks"], 3)
        self.assertEqual(data["results"][1]["evaluation_id"], ev_a.id)
        self.assertEqual(data["results"][1]["status"], "pending")
        self.assertEqual(data["results"][1]["completed_tasks"], 1)
        self.assertEqual(data["results"][1]["total_tasks"], 2)

    def test_get_unknown_id_reported_as_not_found(self):
        response = self.client.get("/batch-evaluation-status/?ids=999999")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"][0]["status"], "not_found")

    def test_get_non_numeric_id_reported_as_not_found(self):
        response = self.client.get("/batch-evaluation-status/?ids=abc")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"][0]["status"], "not_found")

    def test_post_with_list_body(self):
        """POST with a JSON list body is accepted and equivalent to GET."""
        ev = _make_eval(self.user, status="running", total=2, completed=0)

        response = self.client.post(
            "/batch-evaluation-status/",
            data='{"ids": [%d]}' % ev.id,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["evaluation_id"], ev.id)
        self.assertEqual(data["results"][0]["status"], "running")

    def test_post_with_comma_string_body(self):
        """POST with a comma-separated string body is also accepted."""
        ev_a = _make_eval(self.user)
        ev_b = _make_eval(self.user)

        response = self.client.post(
            "/batch-evaluation-status/",
            data='{"ids": "%d,%d"}' % (ev_a.id, ev_b.id),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["results"][0]["evaluation_id"], ev_a.id)
        self.assertEqual(data["results"][1]["evaluation_id"], ev_b.id)

    def test_post_invalid_json_returns_400(self):
        response = self.client.post(
            "/batch-evaluation-status/",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_post_missing_ids_key_returns_400(self):
        response = self.client.post(
            "/batch-evaluation-status/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_other_users_evaluation_is_not_found(self):
        """An evaluation owned by another user must not leak data."""
        other = User.objects.create_user(
            username="other", email="other@example.com", password="pw"
        )
        ev = _make_eval(other, status="completed", total=1, completed=1)

        response = self.client.get("/batch-evaluation-status/?ids=%d" % ev.id)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"][0]["status"], "not_found")
        # No grade/exam name is leaked.
        self.assertNotIn("grade", data["results"][0])
        self.assertNotIn("exam_name", data["results"][0])

    def test_post_large_batch_does_not_hit_url_limit(self):
        """A large number of IDs via POST should not be constrained by the
        URL line-length limit (the original motivation for this change)."""
        evals = [_make_eval(self.user) for _ in range(50)]
        ids_json = "[" + ",".join(str(e.id) for e in evals) + "]"

        response = self.client.post(
            "/batch-evaluation-status/",
            data='{"ids": %s}' % ids_json,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 50)
