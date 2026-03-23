from django.core.exceptions import ValidationError

from genaigrader.models import Course


def get_or_create_course(request):
    """Handles the creation or selection of a course"""
    course_choice = request.POST.get("course_choice")

    if course_choice == "new":
        new_course_name = request.POST.get("new_course", "").strip()
        if not new_course_name:
            raise ValidationError("Course name is required")
        return create_new_course(new_course_name, request.user)
    else:
        return get_existing_course(request.POST.get("course_id"))


def create_new_course(name, user):
    """Creates a new course validating uniqueness"""
    if Course.objects.filter(name__iexact=name, user=user).exists():
        raise ValidationError("This course already exists")
    return Course.objects.create(name=name, user=user)


def get_existing_course(course_id):
    """Retrieves an existing course"""
    return Course.objects.get(id=course_id)
