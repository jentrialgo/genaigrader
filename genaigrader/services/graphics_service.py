from collections import defaultdict

from genaigrader.services.confidence_service import compute_averages


def process_evaluations_for_graphics(evaluations):
    model_values = defaultdict(lambda: {"grades": [], "times": [], "model": None})
    for evaluation in evaluations:
        model_desc = evaluation.model.description
        model_values[model_desc]["grades"].append(evaluation.grade)
        model_values[model_desc]["times"].append(evaluation.time)
        # Store the model object (only need to do this once per model)
        if model_values[model_desc]["model"] is None:
            model_values[model_desc]["model"] = evaluation.model
    return model_values


def compute_model_statistics(model_values):
    model_average_grades, _ = compute_averages(model_values, "grades")
    model_average_times, _ = compute_averages(model_values, "times")

    # Create a simple mapping for sorting
    model_map = {
        data["model"].description: data["model"] for data in model_values.values()
    }

    return (
        sorted(
            model_average_grades,
            key=lambda x: model_map[x["model__description"]].get_sort_key(),
        ),
        sorted(
            model_average_times,
            key=lambda x: model_map[x["model__description"]].get_sort_key(),
        ),
    )
