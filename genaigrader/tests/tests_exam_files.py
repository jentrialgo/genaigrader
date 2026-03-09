from django.test import TestCase

from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from genaigrader.models import Course, Exam, Question, Model
from genaigrader.services.exam_service import process_exam_file
from genaigrader.services.upload_file_service import handle_file_upload
from genaigrader.views.evaluate_views import upload_file
from django.test.client import RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone
VALID_EXAM_FILE_CONTENT = """
What's the PATH?
a) A special file.
b) A file that contains the path to a directory.
c) A file that contains the path to a file.
d) An environment variable.

a
"""

# Question without valid options and correct answer
INVALID_EXAM_FILE_NO_OPTIONS = """
What's the PATH?
"""

# Question without correct answer
INVALID_EXAM_FILE_NO_CORRECT_ANSWER = """
What's the PATH?
a) A special file.
b) A file that contains the path to a directory.
c) A file that contains the path to a file.
d) An environment variable.
"""

INVALID_EXAM_FILE_NO_CORRECT_ANSWER_TWO_QUESTIONS = """
What's the PATH?
a) A special file.
b) A file that contains the path to a directory.
c) A file that contains the path to a file.
d) An environment variable.

Which is not a file system?
a) ext4
b) NTFS
c) FAT32
d) None of the above
d)
"""

class UploadFileTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self._create_user()

    def _create_user(self):
        return User.objects.create_user(username="testuser", password="password")

    def _mock_request(self, file_content):
        """Create a mock request with the necessary parameters."""
        request = self.factory.post(
            "/upload_file/",
            {
                "course_choice": "new",
                "new_course": "Test Course",
                "model": "Test Model",
            },
        )
        uploaded_file = SimpleUploadedFile("test.txt", file_content)
        request.FILES["file"] = uploaded_file

        request.user = self.user
        return request

    @patch("genaigrader.services.exam_service.process_exam_file")
    def test_upload_file_error_does_not_modify_database(self, mock_process_exam_file):
        """This test case checks the behavior when an error occurs during file processing.
        It should not create any exam or questions."""
        # Mock process_exam_file to raise an exception
        mock_process_exam_file.side_effect = Exception("Error processing file")

        # Create a mock uploaded file. it's not important for this test
        # since we are triggering an error, but we need to provide one
        request = self._mock_request(file_content=b"Sample content")

        # Call the view
        upload_file(request)

        # Assert no Exam or Question objects were created
        self.assertEqual(Exam.objects.count(), 0)
        self.assertEqual(Question.objects.count(), 0)

    def test_upload_file_success_creates_exam_and_questions(self):
        """This test case checks the behavior when a valid exam file is uploaded.
        It should return a 200 status code and create an exam and questions."""
        # Create a mock uploaded file
        request = self._mock_request(file_content=VALID_EXAM_FILE_CONTENT.encode())

        # Call the view
        response = upload_file(request)

        # Assert the response status code
        self.assertEqual(response.status_code, 200)

        # Assert that the exam and questions were created
        self.assertEqual(Exam.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 1)

    def __test_updload_file_invalid_exam_file(self, file_content):
        """This test case checks the behavior when an invalid exam file is uploaded.
        It should return a 400 status code and not create any exam or questions."""
        # Create a mock uploaded file with invalid content
        request = self._mock_request(file_content=file_content.encode())

        # Call the view
        response = upload_file(request)

        # Assert the response status code
        self.assertEqual(response.status_code, 400)

        # Assert that no exam or questions were created
        self.assertEqual(Exam.objects.count(), 0)
        self.assertEqual(Question.objects.count(), 0)
        
    def test_upload_file_invalid_exam_file_no_options(self):
        """This test case checks the behavior when a file with a question without options is uploaded.
        It should return a 400 status code and not create any exam or questions."""
        self.__test_updload_file_invalid_exam_file(INVALID_EXAM_FILE_NO_OPTIONS)

    def test_upload_file_invalid_exam_file_no_correct_answer(self):
        """This test case checks the behavior when an exam file with no correct answer is uploaded.
        It should return a 400 status code and not create any exam or questions."""
        self.__test_updload_file_invalid_exam_file(INVALID_EXAM_FILE_NO_CORRECT_ANSWER)

    def test_upload_file_invalid_exam_file_no_correct_answer_two_questions(self):
        """This test case checks the behavior when an exam file with no correct answer for two questions is uploaded.
        It should return a 400 status code and not create any exam or questions."""
        self.__test_updload_file_invalid_exam_file(INVALID_EXAM_FILE_NO_CORRECT_ANSWER_TWO_QUESTIONS)

    def test_empty_exam_file(self):
        """This test case checks the behavior when an empty exam file is uploaded.
        It should return a 400 status code and not create any exam or questions."""
        self.__test_updload_file_invalid_exam_file("")

    @patch("genaigrader.services.upload_file_service.is_unique_exam")
    def test_duplicate_exam_evaluation_returns_409(self, mock_is_unique):
        """This test verifies that uploading the exact same exam for the same model
        returns a 409 Conflict status code and prevents duplication."""
        mock_is_unique.return_value = False

        request = self._mock_request(file_content=VALID_EXAM_FILE_CONTENT.encode())
        from genaigrader.services.upload_file_service import handle_file_upload
        response = handle_file_upload(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Exam.objects.count(), 0)


class TestExamService(TestCase):
    def test_invalid_exam_file_no_options(self):
        """This test case checks the behavior when an exam file with no options is processed.
        It should raise a ValueError."""
        file_path = "genaigrader/tests/exam_files/invalid_exam_file_no_options.txt"

        # Assert that an exception is raised when calling process_exam_file
        with self.assertRaises(ValueError):
            process_exam_file(file_path)


