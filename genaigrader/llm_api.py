import ollama
import openai
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError


class LlmApi:
    def __init__(self, model_obj):
        """
        Initialize the LlmApi with a model object.

        Parameters:
        - model_obj: An object representing the model. It must have the following attributes:
            - description (str): The model name or identifier.
            - is_external (bool): Indicates if the model is external (e.g., OpenAI) or local (e.g., Ollama).
            - api_url (str, optional): Required if is_external=True. The base URL of the external API.
            - api_key (str, optional): Required if is_external=True. The authentication token for the external API.
        """
        self.model_obj = model_obj
        self.client = None  # Initialize client lazily after successful validation.

    def validate(self):
        """
        Validates the model object's required fields based on whether it's external or local.

        Raises:
        - ValueError: If any required fields are missing or incorrectly formatted.
        """
        errors = []

        if not self.model_obj.description:
            errors.append("Model name (description) is required")

        if self.model_obj.is_external:
            if not self.model_obj.api_url:
                errors.append("API URL is required for external models")
            else:
                try:
                    URLValidator()(self.model_obj.api_url)
                except ValidationError:
                    errors.append("API URL is not valid")

            if not self.model_obj.api_key:
                errors.append("API key is required for external models")

            # Validate connectivity and authentication for external models.
            if not errors:
                try:
                    # Create the client only when basic validation passes.
                    self.client = openai.OpenAI(
                        api_key=self.model_obj.api_key,
                        base_url=self.model_obj.api_url
                    )
                    # Perform a connectivity test request.
                    self.client.models.list()  # External API connectivity test.
                except openai.AuthenticationError:
                    errors.append("Invalid or unauthorized API key")
                except openai.APIConnectionError:
                    errors.append(f"Failed to connect to the API at {self.model_obj.api_url}")
                except openai.NotFoundError:
                    errors.append(f"Model '{self.model_obj.description}' not found on the API")
                except Exception as e:
                    errors.append(f"Error trying to validate model: {e}")
        if errors:
            raise ValueError("\n".join([f"Model error: {e}" for e in errors]))

    def _strip_think_tags(self, text):
        """
        Removes all <think>...</think> blocks from the text.
        """
        import re
        return re.sub(r'<think>[\s\S]*?</think>', '', text)

    def _yield_thinking_aware(self, stream, get_content):
        """
        If the first chunk starts with <think>, buffer until </think> and yield only what comes after (ignoring blank lines).
        Otherwise, yield all content as it arrives (ignoring blank lines).
        """
        buffer = ""
        first_chunk = True
        buffering = False
        for chunk in stream:
            content = get_content(chunk)
            if not content:
                continue
            if first_chunk:
                first_chunk = False
                if content.lstrip().startswith('<think>'):
                    buffering = True
                    buffer += content
                    continue  # Don't yield yet
                else:
                    # Only yield non-blank lines
                    for line in content.splitlines():
                        if line.strip():
                            yield line
                    continue
            if buffering:
                buffer += content
                end_tag = buffer.find('</think>')
                if end_tag == -1:
                    # Still inside <think> block
                    continue
                # Found </think>, yield only what comes after
                after = buffer[end_tag + len('</think>'):]
                for line in after.splitlines():
                    if line.strip():
                        yield line
                buffering = False
                buffer = ""
            else:
                # Only yield non-blank lines
                for line in content.splitlines():
                    if line.strip():
                        yield line

    def _use_external_model(self, prompt):
        """
        Calls an external (OpenAI-compatible) API to generate a response to the prompt.

        Parameters:
        - prompt (str): The user input to be sent to the external model.

        Yields:
        - str: A stream of response chunks from the model (partial content).
        
        Raises:
        - ValueError: If connection/authentication/model errors occur.
        """
        if not self.client:
            # This should ideally be caught by validate() before this point.
            raise ValueError("OpenAI client not initialized. Validation might have failed or was skipped.")

        response = self.client.chat.completions.create(
            model=self.model_obj.description,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        yield from self._yield_thinking_aware(response, lambda chunk: chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None)

    def _use_local_model(self, prompt):
        """
        Calls a local Ollama model to generate a response to the prompt.

        Parameters:
        - prompt (str): The user input to be sent to the local model.

        Yields:
        - str: A stream of response chunks from the local model.
        
        Raises:
        - ValueError: If an error occurs during local model execution.
        """
        response_stream = ollama.chat(
            model=self.model_obj.description,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        yield from self._yield_thinking_aware(response_stream, lambda chunk: chunk['message']['content'])

    def generate_response(self, prompt):
        """
        Main method to generate a response using either a local or external model.

        Parameters:
        - prompt (str): The user message or question.

        Yields:
        - str: A stream of generated text from the selected model.
        
        Raises:
        - ValueError: If model validation fails (e.g., missing API key, invalid URL).
        - ollama.ResponseError: If an error occurs while calling the local model.
        - openai.error.OpenAIError: If an error occurs while calling the external model.

        Example:
        >>> llm = LlmApi(model_obj)
        >>> try:
        ...     for chunk in llm.generate_response("What is the capital of France?"):
        ...         print(chunk, end="")
        ... except Exception as e:
        ...     print(f"An error occurred: {e}")
        """
        self.validate()
        if self.model_obj.is_external:
            yield from self._use_external_model(prompt)
        else:
            yield from self._use_local_model(prompt)
