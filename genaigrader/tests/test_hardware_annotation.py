import json
from unittest.mock import patch, Mock
from django.test import TestCase
from genaigrader.models import Course, Exam, Model, Evaluation, Question, QuestionOption, User
from genaigrader.services.hardware_annotation_service import (
    get_system_hardware_info, 
    get_ollama_hardware_info,
    get_hardware_annotation
)


class HardwareAnnotationTest(TestCase):
    def setUp(self):
        """Set up test data"""
        # Create a user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword123'
        )
        
        # Create a course
        self.course = Course.objects.create(
            name='Test Course',
            user=self.user
        )
        
        # Create an exam
        self.exam = Exam.objects.create(
            description='Test Exam',
            course=self.course,
            user=self.user
        )
        
        # Create local and external models
        self.local_model = Model.objects.create(
            description='llama3.2:3b'
        )
        
        self.external_model = Model.objects.create(
            description='gpt-4o-mini',
            api_url='https://api.openai.com/v1/',
            api_key='sk-test123',
            user=self.user
        )

    def test_get_system_hardware_info(self):
        """Test that system hardware info can be collected"""
        info = get_system_hardware_info()
        
        self.assertIsInstance(info, dict)
        # Should have basic system info
        self.assertIn('system', info)
        self.assertIn('machine', info)
        self.assertIn('cpu_count', info)

    @patch('genaigrader.services.hardware_annotation_service.ollama.Client')
    def test_get_ollama_hardware_info_success(self, mock_client_class):
        """Test successful ollama hardware info collection"""
        # Mock the ollama client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.ps.return_value = {
            'models': [
                {'name': 'llama3.2:3b', 'size_vram': 3221225472}  # 3GB in bytes
            ]
        }
        
        # Mock requests for version endpoint
        with patch('genaigrader.services.hardware_annotation_service.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'version': '0.1.0'}
            mock_get.return_value = mock_response
            
            info = get_ollama_hardware_info()
        
        self.assertIsInstance(info, dict)
        self.assertTrue(info.get('ollama_running'))
        self.assertEqual(info.get('gpu_vram_mb'), 3072)  # 3GB in MB
        self.assertEqual(info.get('ollama_version'), '0.1.0')

    @patch('genaigrader.services.hardware_annotation_service.ollama.Client')
    def test_get_ollama_hardware_info_failure(self, mock_client_class):
        """Test ollama hardware info collection when ollama is not available"""
        # Mock ollama client to raise exception
        mock_client_class.side_effect = Exception("Connection failed")
        
        info = get_ollama_hardware_info()
        
        self.assertEqual(info, {})

    def test_get_hardware_annotation_external_model(self):
        """Test that external models return None for hardware annotation"""
        annotation = get_hardware_annotation(self.external_model)
        
        self.assertIsNone(annotation)

    @patch('genaigrader.services.hardware_annotation_service.get_ollama_hardware_info')
    @patch('genaigrader.services.hardware_annotation_service.get_system_hardware_info')
    def test_get_hardware_annotation_local_model(self, mock_system_info, mock_ollama_info):
        """Test hardware annotation for local models"""
        # Mock the info functions
        mock_system_info.return_value = {
            'system': 'Linux',
            'machine': 'x86_64',
            'cpu_count': 8
        }
        mock_ollama_info.return_value = {
            'ollama_running': True,
            'gpu_vram_mb': 8192
        }
        
        annotation = get_hardware_annotation(self.local_model)
        
        self.assertIsNotNone(annotation)
        # Should be valid JSON
        data = json.loads(annotation)
        self.assertEqual(data['system'], 'Linux')
        self.assertEqual(data['machine'], 'x86_64')
        self.assertEqual(data['cpu_count'], 8)
        self.assertTrue(data['ollama_running'])
        self.assertEqual(data['gpu_vram_mb'], 8192)

    @patch('genaigrader.services.hardware_annotation_service.get_ollama_hardware_info')
    @patch('genaigrader.services.hardware_annotation_service.get_system_hardware_info')  
    def test_get_hardware_annotation_no_info(self, mock_system_info, mock_ollama_info):
        """Test hardware annotation when no info is available"""
        # Mock empty responses
        mock_system_info.return_value = {}
        mock_ollama_info.return_value = {}
        
        annotation = get_hardware_annotation(self.local_model)
        
        self.assertIsNone(annotation)

    def test_evaluation_model_has_hardware_info_field(self):
        """Test that the Evaluation model has a hardware_info field"""
        # Create an evaluation with hardware info
        test_hardware_info = json.dumps({
            'system': 'Linux',
            'machine': 'x86_64',
            'cpu_count': 8,
            'ollama_running': True
        })
        
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.local_model,
            exam=self.exam,
            hardware_info=test_hardware_info
        )
        
        # Verify the hardware_info field was saved correctly
        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertEqual(saved_evaluation.hardware_info, test_hardware_info)
        
        # Verify we can parse it back to dict
        parsed_info = json.loads(saved_evaluation.hardware_info)
        self.assertEqual(parsed_info['system'], 'Linux')
        self.assertEqual(parsed_info['cpu_count'], 8)

    def test_evaluation_hardware_info_field_can_be_null(self):
        """Test that the hardware_info field can be null/empty"""
        evaluation = Evaluation.objects.create(
            prompt="Test prompt",
            ev_date="2024-01-01T12:00:00Z",
            grade=8.5,
            time=45.2,
            model=self.local_model,
            exam=self.exam,
            hardware_info=None
        )
        
        saved_evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertIsNone(saved_evaluation.hardware_info)