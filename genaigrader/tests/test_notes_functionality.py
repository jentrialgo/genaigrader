from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import Mock, patch
from genaigrader.models import Course, Exam, Question, QuestionOption, Model, Evaluation
from genaigrader.services.stream_service import stream_responses


class NotesfunctionalityTest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='password')
        self.course = Course.objects.create(name='Test Course', user=self.user)
        self.exam = Exam.objects.create(course=self.course, description='Test Exam', user=self.user)
        self.model = Model.objects.create(description='Test Model')
        
        # Create a question with options
        self.question = Question.objects.create(
            statement='What is 2+2?',
            exam=self.exam
        )
        
        self.option_a = QuestionOption.objects.create(content='a) 3', question=self.question)
        self.option_b = QuestionOption.objects.create(content='b) 4', question=self.question)
        self.question.correct_option = self.option_b
        self.question.save()

    def test_evaluation_model_has_notes_field(self):
        """Test that the Evaluation model has a notes field with correct properties"""
        # Create an evaluation with notes
        test_notes = "This exam was conducted on high-performance hardware"
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.model,
            exam=self.exam,
            notes=test_notes
        )
        
        # Verify the notes field was saved correctly
        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertEqual(saved_evaluation.notes, test_notes)
        
    def test_evaluation_notes_field_can_be_null(self):
        """Test that the notes field can be null/empty"""
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.model,
            exam=self.exam,
            notes=None
        )
        
        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertIsNone(saved_evaluation.notes)
        
    @patch('genaigrader.services.stream_service.generate_prompt')
    @patch('genaigrader.services.stream_service.get_evaluation_ollama_version')
    @patch('genaigrader.services.stream_service.get_hardware_annotation')
    def test_stream_responses_handles_notes_parameter(self, mock_hardware_annotation, mock_ollama_version, mock_generate_prompt):
        """Test that stream_responses correctly handles the notes parameter"""
        # Mock dependencies
        mock_ollama_version.return_value = "1.0.0"
        mock_hardware_annotation.return_value = '{"system": "Linux", "cpu_count": 4}'
        mock_generate_prompt.return_value = {
            'prompt': 'Test prompt',
            'question_prompt': 'What is 2+2?',
            'user_prompt': 'Test user prompt'
        }
        
        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ['b']
        
        test_notes = "Hardware: AMD Ryzen 9, 32GB RAM"
        questions = [self.question]
        user_prompt = "Test prompt"
        
        # Collect all chunks from the stream
        chunks = list(stream_responses(questions, user_prompt, mock_llm, 1, self.exam, test_notes))
        
        # Verify that an evaluation was created with the notes
        evaluations = Evaluation.objects.filter(exam=self.exam)
        self.assertEqual(evaluations.count(), 1)
        
        created_evaluation = evaluations.first()
        self.assertEqual(created_evaluation.notes, test_notes)
        
    @patch('genaigrader.services.stream_service.generate_prompt')
    @patch('genaigrader.services.stream_service.get_evaluation_ollama_version')
    @patch('genaigrader.services.stream_service.get_hardware_annotation')
    def test_stream_responses_works_without_notes(self, mock_hardware_annotation, mock_ollama_version, mock_generate_prompt):
        """Test that stream_responses works correctly when no notes are provided"""
        # Mock dependencies
        mock_ollama_version.return_value = "1.0.0"
        mock_hardware_annotation.return_value = None  # No hardware annotation
        mock_generate_prompt.return_value = {
            'prompt': 'Test prompt',
            'question_prompt': 'What is 2+2?',
            'user_prompt': 'Test user prompt'
        }
        
        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model_obj = self.model
        mock_llm.generate_response.return_value = ['b']
        
        questions = [self.question]
        user_prompt = "Test prompt"
        
        # Call without notes parameter (should default to None)
        chunks = list(stream_responses(questions, user_prompt, mock_llm, 1, self.exam))
        
        # Verify that an evaluation was created with null notes
        evaluations = Evaluation.objects.filter(exam=self.exam)
        self.assertEqual(evaluations.count(), 1)
        
        created_evaluation = evaluations.first()
        self.assertIsNone(created_evaluation.notes)