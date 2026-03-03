def generate_prompt(question, user_prompt):
    """
    Generates a structured prompt to be sent to the language model.

    Parameters:
    - question: Question instance containing the statement and options.
    - user_prompt: Optional user-defined instruction to prepend to the prompt.

    Returns:
    - dict with full prompt and separated components.
    """
    prompt = ""
    user_prompt_part = user_prompt or ""
    
    user_prompt_part += (
        "Te voy a pasar una pregunta de test y tienes que responderme con qué opción es la correcta. "
        "Sólo debes decirme la opción, por ejemplo 'a', absolutamente nada más.\n"
    )

    question_prompt_part = question.statement + "\n"

    for option in question.questionoption_set.all().order_by('content'):
        question_prompt_part += f"{option.content}\n"

    prompt = user_prompt_part + question_prompt_part

    return {
        'prompt': prompt,
        'user_prompt': user_prompt_part,
        'question_prompt': question_prompt_part
    }