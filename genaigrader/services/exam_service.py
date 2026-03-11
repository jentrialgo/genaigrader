from typing import List, Dict
from ..models import Exam
import re


def resolve_exam_name(uploaded_file, request):
    """Resolve exam name using user input first, falling back to uploaded file name."""
    exam_name = request.POST.get("user_exam", "").strip()
    return exam_name if exam_name else uploaded_file.name

def create_exam(uploaded_file, course, user, request):
    description = resolve_exam_name(uploaded_file, request)
    return Exam(
        description=description,
        course=course,
        user=user
    )  # Returns unsaved instance

def process_exam_file(file_path) -> List[Dict]:
    """Process file and validate format, returns clean data without DB interaction"""
    questions_data = []
    statement = []
    current_question = None
    state = "statement"
    line_number = 0
    has_content = False

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_number += 1
            stripped_line = line.strip()
            if stripped_line:
                has_content = True

            if state == "statement":
                if stripped_line and re.match(r'^[a-zA-Z]\)', stripped_line):
                    if not statement:  # Validate that there is a statement
                        raise ValueError(f"Line {line_number}: Question missing statement")
                    
                    current_question = {
                        'statement': "\n".join(statement).strip(),
                        'options': [stripped_line],
                        'correct_option': None
                    }
                    state = "options"
                    statement = []
                else:
                    if stripped_line:  # Ignore blank lines in the statement
                        statement.append(stripped_line)

            elif state == "options":
                if not stripped_line:
                    # Transition to correct answer
                    if len(current_question['options']) < 2:
                        raise ValueError(
                            f"Line {line_number}: Minimum 2 options required. Question: '{current_question['statement'][:30]}...'"
                        )
                    state = "correct"
                else:
                    if re.match(r'^[a-zA-Z]\)', stripped_line):
                        current_question['options'].append(stripped_line)
                    else:
                        # Process as correct answer
                        correct_option = stripped_line.lower().strip()
                        option_letters = [opt.split(')')[0].strip().lower() for opt in current_question['options']]
                        
                        if correct_option not in option_letters:
                            raise ValueError(
                                f"Line {line_number}: Invalid correct option '{correct_option}'. Valid options: {option_letters}"
                            )
                        
                        current_question['correct_option'] = correct_option
                        questions_data.append(current_question)
                        current_question = None
                        state = "statement"

            elif state == "correct":
                if stripped_line:
                    correct_option = stripped_line.lower().strip()
                    option_letters = [opt.split(')')[0].strip().lower() for opt in current_question['options']]
                    
                    if correct_option not in option_letters:
                        raise ValueError(
                            f"Line {line_number}: Invalid correct option '{correct_option}'. Valid options: {option_letters}"
                        )
                    
                    current_question['correct_option'] = correct_option
                    questions_data.append(current_question)
                    current_question = None
                    state = "statement"

        # Final file validation
        if not has_content:
            raise ValueError("File is completely empty")
        
        if state != "statement":
            raise ValueError("Invalid format: incomplete final question")
        
        if not questions_data:
            raise ValueError("File contains no valid questions")

    return questions_data