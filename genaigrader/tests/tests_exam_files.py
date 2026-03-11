import json

from django.test import TestCase

from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from genaigrader.models import Course, Exam, Question
from genaigrader.services.exam_service import process_exam_file
from genaigrader.views.evaluate_views import upload_file
from django.test.client import RequestFactory
from django.contrib.auth.models import User

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
        self.course = Course.objects.create(name="Test Course", user=self.user)

    def _create_user(self):
        return User.objects.create_user(username="testuser", password="password")

    def _mock_request(self, file_content, file_name="test.txt", **extra_post_data):
        """Create a mock request with the necessary parameters."""
        post_data = {
            "course_choice": "existing",
            "course_id": str(self.course.id),
            "model": "Test Model",
        }
        post_data.update(extra_post_data)

        request = self.factory.post(
            "/upload_file/",
            post_data,
        )
        uploaded_file = SimpleUploadedFile(file_name, file_content)
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

    def test_upload_blocks_duplicate_exam_name_from_file_name(self):
        """Uploading with an existing exam name in the same course returns 409 and avoids duplicates."""
        existing_exam = Exam.objects.create(description="test.txt", course=self.course, user=self.user)

        request = self._mock_request(file_content=VALID_EXAM_FILE_CONTENT.encode(), file_name="test.txt")
        response = upload_file(request)

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertEqual(payload["error"], "duplicate_exam")
        self.assertEqual(payload["existing_exam_id"], existing_exam.id)
        self.assertEqual(payload["exam_name"], "test.txt")
        self.assertEqual(payload["course_name"], self.course.name)
        self.assertEqual(payload["message"], "An exam with this name already exists in this course.")
        self.assertEqual(Exam.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 0)

    def test_upload_blocks_duplicate_exam_name_from_user_exam(self):
        """The user_exam field has priority over file name when checking for conflicts."""
        existing_exam = Exam.objects.create(description="Midterm 1", course=self.course, user=self.user)

        request = self._mock_request(
            file_content=VALID_EXAM_FILE_CONTENT.encode(),
            file_name="another_file.txt",
            user_exam="Midterm 1",
        )
        response = upload_file(request)

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertEqual(payload["error"], "duplicate_exam")
        self.assertEqual(payload["existing_exam_id"], existing_exam.id)
        self.assertEqual(payload["exam_name"], "Midterm 1")
        self.assertEqual(payload["course_name"], self.course.name)
        self.assertEqual(payload["message"], "An exam with this name already exists in this course.")
        self.assertEqual(Exam.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 0)

    def test_upload_allows_same_exam_name_in_different_course(self):
        """Exam names are unique per course, so same name in another course is allowed."""
        other_course = Course.objects.create(name="Other Course", user=self.user)
        Exam.objects.create(description="test.txt", course=self.course, user=self.user)

        request = self.factory.post(
            "/upload_file/",
            {
                "course_choice": "existing",
                "course_id": str(other_course.id),
                "model": "Test Model",
            },
        )
        request.FILES["file"] = SimpleUploadedFile("test.txt", VALID_EXAM_FILE_CONTENT.encode())
        request.user = self.user

        response = upload_file(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Exam.objects.filter(description="test.txt").count(), 2)

class TestExamService(TestCase):
    def test_invalid_exam_file_no_options(self):
        """This test case checks the behavior when an exam file with no options is processed.
        It should raise a ValueError."""
        file_path = "genaigrader/tests/exam_files/invalid_exam_file_no_options.txt"

        # Assert that an exception is raised when calling process_exam_file
        with self.assertRaises(ValueError):
            process_exam_file(file_path)


