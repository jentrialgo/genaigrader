from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class Exam(models.Model):
    id = models.AutoField(primary_key=True)
    description = models.CharField(max_length=255)
    course = models.ForeignKey(Course, on_delete=models.CASCADE) 
    user = models.ForeignKey(User, on_delete=models.CASCADE)  

    def __str__(self):
        return self.description

class QuestionOption(models.Model):
    id = models.AutoField(primary_key=True)
    content = models.CharField(max_length=255)
    question = models.ForeignKey('Question', on_delete=models.CASCADE)

    def __str__(self):
        return self.content

class Question(models.Model):
    id = models.AutoField(primary_key=True)
    statement = models.TextField()
    correct_option = models.ForeignKey(QuestionOption, on_delete=models.CASCADE, null=True, related_name='correct_option_for')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    
    def __str__(self):
        return self.statement[:50]  

class Model(models.Model):
    id = models.AutoField(primary_key=True)
    description = models.CharField(max_length=255)

    # Optional fields for external models
    api_url = models.URLField(max_length=500, null=True, blank=True)
    api_key = models.CharField(max_length=255, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def clean(self):
        super().clean()
        if self.is_external and not self.user:
            raise ValidationError("The 'user' field is required for external models")
        if not self.is_external and self.user:
            raise ValidationError("The 'user' field should only be used for external models")
        
    def __str__(self):
        return self.description

    @property
    def is_external(self):
        return self.api_url is not None and self.api_key is not None

    def _extract_model_info(self):
        """
        Extract model family, size, and variant information from local model name.
        Returns (family, size_value, size_unit, variant, is_external)
        """
        model_name = self.description

        if self.is_external:
            return (model_name, 0, '', '', True)

        # Local models pattern: family:size or family:size-variant
        # Examples: gemma3:1b, deepseek-r1:7b, phi4-mini-reasoning, llama3.2:3b

        # Handle models without size (like phi4-mini-reasoning)
        if ':' not in model_name:
            return (model_name, 0, '', '', False)

        family, size_part = model_name.split(':', 1)

        # Extract size and variant from size_part
        # Examples: "1b", "7b", "1b-it-qat", "27b-it-qat"
        size_match = re.match(r'^(\d+(?:\.\d+)?)([a-zA-Z]*)(.*)', size_part)

        if size_match:
            size_value = float(size_match.group(1))
            size_unit = size_match.group(2)
            variant = size_match.group(3)
            return (family, size_value, size_unit, variant, False)
        else:
            # If no size match, treat entire size_part as variant
            return (family, 0, '', size_part, False)

    def get_sort_key(self):
        """
        Generate a sort key for this model object.
        Local models are sorted first by family, then by size, then by variant.
        External models come last and are sorted alphabetically.
        """
        if self.is_external:
            # External models go last, sorted alphabetically
            return (1, self.description.lower())
        else:
            # Local models go first
            # Extract model information from name for local models
            family, size_value, size_unit, variant, _ = self._extract_model_info()
            # Sort by: family, size_value, size_unit (b < others), variant
            size_unit_priority = 0 if size_unit.lower() == 'b' else 1
            return (0, family.lower(), size_value, size_unit_priority, size_unit.lower(), variant.lower())

class Evaluation(models.Model):
    id = models.AutoField(primary_key=True)
    prompt = models.TextField()
    ev_date = models.DateTimeField()
    grade = models.FloatField()
    time = models.FloatField()
    model = models.ForeignKey(Model, on_delete= models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    ollama_version = models.CharField(max_length=50, null=True, blank=True, help_text="Version of Ollama used (null for external models)")

    def __str__(self):
        return f'{self.prompt} {self.grade}'

class QuestionEvaluation(models.Model):
    id = models.AutoField(primary_key=True)
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    question_option = models.ForeignKey(QuestionOption, on_delete=models.CASCADE)

    def __str__(self):
        return f"Evaluation {self.evaluation.id}, Question {self.question.id}, Option {self.question_option.id}"