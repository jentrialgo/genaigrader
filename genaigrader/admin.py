from django.contrib import admin

from .models import (
    Course,
    Evaluation,
    Exam,
    Model,
    Question,
    QuestionEvaluation,
    QuestionOption,
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "show_exams")
    search_fields = ("name",)

    def show_exams(self, obj):
        return ", ".join([exam.description for exam in obj.exam_set.all()])

    show_exams.short_description = "Exámenes"


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("id", "description", "course_id", "user", "show_questions")
    list_filter = ("course_id", "user")
    search_fields = ("description",)

    def show_questions(self, obj):
        return ", ".join(
            [question.statement[:50] for question in obj.question_set.all()]
        )

    show_questions.short_description = "Preguntas"


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "statement", "correct_option_id", "exam_id", "show_options")
    list_filter = ("exam_id",)
    search_fields = ("statement",)

    def show_options(self, obj):
        return ", ".join([option.content for option in obj.questionoption_set.all()])

    show_options.short_description = "Opciones"


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("id", "content", "question_id", "show_related_question")
    search_fields = ("content",)

    def show_related_question(self, obj):
        return obj.question.statement[:50]

    show_related_question.short_description = "Pregunta Relacionada"


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = ("id", "description", "show_evaluations")
    search_fields = ("description",)

    def show_evaluations(self, obj):
        return ", ".join(
            [evaluation.prompt[:50] for evaluation in obj.evaluation_set.all()]
        )

    show_evaluations.short_description = "Evaluaciones"


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "prompt",
        "ev_date",
        "grade",
        "time",
        "model_id",
        "show_model_description",
        "exam_id",
        "show_question_evaluations",
    )
    list_filter = ("model_id", "exam_id")
    search_fields = (
        "prompt",
        "model__description",
    )

    def show_question_evaluations(self, obj):
        return ", ".join(
            [
                f"Q{qe.question.id} (O{qe.question_option_id if qe.question_option_id is not None else 'None'})"
                for qe in obj.questionevaluation_set.all()
            ]
        )

    show_question_evaluations.short_description = "Evaluaciones de Preguntas"

    def show_model_description(self, obj):
        return obj.model.description

    show_model_description.short_description = "Model Description"


@admin.register(QuestionEvaluation)
class QuestionEvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "evaluation_id",
        "question_id",
        "question_option_id",
        "show_related_info",
    )
    list_filter = ("evaluation_id", "question_id", "question_option_id")
    search_fields = ("evaluation_id__id", "question_id__id", "question_option_id__id")

    def show_related_info(self, obj):
        option_text = (
            obj.question_option.content if obj.question_option else "No matched option"
        )
        return f"Evaluation: {obj.evaluation.prompt[:50]}, Question: {obj.question.statement[:50]}, Option: {option_text}"

    show_related_info.short_description = "Información Relacionada"
