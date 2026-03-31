from collections import defaultdict

from genaigrader.services import model_service
from genaigrader.services.confidence_service import compute_averages


def process_evaluations_for_graphics(evaluations):
    model_values = defaultdict(lambda: {"grades": [], "times": [], "model": None})
    for evaluation in evaluations:
        model_desc = evaluation.model.description
        model_values[model_desc]["grades"].append(evaluation.grade)
        model_values[model_desc]["times"].append(evaluation.time)
        if model_values[model_desc]["model"] is None:
            model_values[model_desc]["model"] = evaluation.model
    return model_values


def _enrich_and_sort_stats(stats_list, model_map):
    """Internal helper to add metadata and sort stats by model key."""
    for entry in stats_list:
        model = model_map[entry["model__description"]]

        family_name = getattr(model, "family_name", None)
        if not family_name and hasattr(model, "family") and model.family:
            family_name = model.family.name

        entry.update(
            {
                "model_color": model_service.resolve_model_color(model),
                "model_family": family_name or "Unknown",
                "model_parameters": model.parameter_count or 0,
            }
        )
    return sorted(
        stats_list, key=lambda x: model_map[x["model__description"]].get_sort_key()
    )


def compute_model_statistics(model_values):
    model_average_grades, _ = compute_averages(model_values, "grades")
    model_average_times, _ = compute_averages(model_values, "times")

    model_map = {
        data["model"].description: data["model"] for data in model_values.values()
    }

    return (
        _enrich_and_sort_stats(model_average_grades, model_map),
        _enrich_and_sort_stats(model_average_times, model_map),
    )
