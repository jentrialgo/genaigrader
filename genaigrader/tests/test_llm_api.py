from unittest.mock import Mock, patch

from django.test import TestCase

import genaigrader.llm_api as llm_api_module
from genaigrader.llm_api import LlmApi, _unload_local_model


def _make_local_model_obj(model_id, description, is_external=False):
    obj = Mock()
    obj.id = model_id
    obj.description = description
    obj.is_external = is_external
    obj.api_url = ""
    obj.api_key = ""
    obj._validated = True
    return obj


class UnloadLocalModelTest(TestCase):
    def test_unload_calls_generate_with_keep_alive_zero(self):
        client = Mock()
        _unload_local_model(client, "llama3.2:1b")
        client.generate.assert_called_once_with(
            model="llama3.2:1b", prompt="", keep_alive=0
        )

    def test_unload_swallows_exceptions(self):
        client = Mock()
        client.generate.side_effect = RuntimeError("Ollama is down")
        _unload_local_model(client, "llama3.2:1b")


class UseLocalModelUnloadTest(TestCase):
    def setUp(self):
        llm_api_module._last_local_model_name = None

    def tearDown(self):
        llm_api_module._last_local_model_name = None

    @patch("genaigrader.llm_api.ollama.Client")
    def test_first_call_no_unload(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.return_value = iter([{"message": {"content": "a"}}])

        model_obj = _make_local_model_obj(1, "model-a")
        api = LlmApi(model_obj)
        list(api._use_local_model("test prompt"))

        mock_client.generate.assert_not_called()
        self.assertEqual(llm_api_module._last_local_model_name, "model-a")

    @patch("genaigrader.llm_api.ollama.Client")
    def test_same_model_no_unload(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.return_value = iter([{"message": {"content": "a"}}])

        llm_api_module._last_local_model_name = "model-a"

        model_obj = _make_local_model_obj(1, "model-a")
        api = LlmApi(model_obj)
        api.ollama_client = mock_client
        list(api._use_local_model("test prompt"))

        mock_client.generate.assert_not_called()
        self.assertEqual(llm_api_module._last_local_model_name, "model-a")

    @patch("genaigrader.llm_api.ollama.Client")
    def test_different_model_triggers_unload(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.return_value = iter([{"message": {"content": "b"}}])

        llm_api_module._last_local_model_name = "model-a"

        model_obj = _make_local_model_obj(2, "model-b")
        api = LlmApi(model_obj)
        api.ollama_client = mock_client
        list(api._use_local_model("test prompt"))

        mock_client.generate.assert_called_once_with(
            model="model-a", prompt="", keep_alive=0
        )
        self.assertEqual(llm_api_module._last_local_model_name, "model-b")

    @patch("genaigrader.llm_api.ollama.Client")
    def test_unload_failure_does_not_break_inference(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        mock_client.generate.side_effect = RuntimeError("unload failed")
        mock_client.chat.return_value = iter([{"message": {"content": "b"}}])

        llm_api_module._last_local_model_name = "model-a"

        model_obj = _make_local_model_obj(2, "model-b")
        api = LlmApi(model_obj)
        api.ollama_client = mock_client
        result = list(api._use_local_model("test prompt"))

        self.assertEqual(result, ["b"])
        self.assertEqual(llm_api_module._last_local_model_name, "model-b")
