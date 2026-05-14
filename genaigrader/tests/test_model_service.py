import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from genaigrader.models import Model
from genaigrader.services.model_service import pull_model

User = get_user_model()


class PullModelTest(TestCase):
    @patch("genaigrader.services.model_service.requests.post")
    def test_pull_model_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            json.dumps({"status": "pulling"}),
            json.dumps({"status": "success"}),
        ]
        mock_post.return_value = mock_response

        result = pull_model("llama3.2:1b")

        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["model"], "llama3.2:1b")
        self.assertIn("model_id", result)

        model = Model.objects.get(id=result["model_id"])
        self.assertEqual(model.description, "llama3.2:1b")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs[1]["json"]["name"], "llama3.2:1b")

    @patch("genaigrader.services.model_service.requests.post")
    def test_pull_model_ollama_http_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            pull_model("broken-model")

        self.assertIn("500", str(context.exception))
        self.assertFalse(Model.objects.filter(description="broken-model").exists())

    @patch("genaigrader.services.model_service.requests.post")
    def test_pull_model_ollama_stream_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            json.dumps({"status": "pulling"}),
            json.dumps({"error": "download interrupted"}),
        ]
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            pull_model("failing-model")

        self.assertIn("download interrupted", str(context.exception))
        self.assertFalse(Model.objects.filter(description="failing-model").exists())

    @patch("genaigrader.services.model_service.requests.post")
    def test_pull_model_incomplete_download(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            json.dumps({"status": "pulling"}),
        ]
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            pull_model("incomplete-model")

        self.assertIn("did not complete", str(context.exception))
        self.assertFalse(Model.objects.filter(description="incomplete-model").exists())

    @patch("genaigrader.services.model_service.requests.post")
    def test_pull_model_json_decode_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            "not valid json{{{",
        ]
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            pull_model("bad-json-model")

        self.assertIn("Error reading Ollama response", str(context.exception))
        self.assertFalse(Model.objects.filter(description="bad-json-model").exists())
