import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django_q.models import Task

from genaigrader.models import Evaluation

# Maximum number of IDs accepted by the batch endpoint. The previous GET
# implementation was constrained by the URL line-length limit (~8 KB); using a
# POST body removes that limit but we still cap the input to bound the work.
MAX_BATCH_IDS = 1000


def _can_view_task(task, user):
    """
    Verify that *user* is authorised to inspect *task*.

    Evaluation tasks use ``group="eval:<evaluation_id>"``.
    For those we look up the Evaluation and assert ownership.
    Tasks without a group (e.g. model downloads) are public to all
    authenticated users. Unrecognised group strings are denied.
    """
    if not task:
        return False
    if not task.group:
        return True

    if not isinstance(task.group, str) or not task.group.startswith("eval:"):
        return False

    try:
        eval_id = int(task.group.split(":", 1)[1])
        evaluation = Evaluation.objects.select_related("exam__course").get(id=eval_id)
        return evaluation.exam.course.user == user
    except (ValueError, TypeError, ObjectDoesNotExist, IndexError):
        return False


@login_required
def task_status(request, task_id):
    task = Task.objects.filter(id=task_id).first()
    if task is not None:
        if not _can_view_task(task, request.user):
            return JsonResponse({"status": "error", "message": "Forbidden"}, status=403)

        if task.success:
            result = task.result
        elif task.result is not None:
            result = str(task.result)
        else:
            result = "Task failed"

        return JsonResponse(
            {
                "task_id": task.id,
                "name": task.name,
                "status": "success" if task.success else "failed",
                "started": task.started.isoformat() if task.started else None,
                "stopped": task.stopped.isoformat() if task.stopped else None,
                "result": result,
            }
        )

    return JsonResponse({"task_id": task_id, "status": "queued"})


@login_required
def batch_task_status(request):
    """
    Return the current status for a batch of django-q2 task IDs.

    Accepts either:

    * ``GET /batch-task-status/?ids=<id1>,<id2>`` (kept for backwards
      compatibility; subject to the URL line-length limit).
    * ``POST /batch-task-status/`` with a JSON body
      ``{"ids": ["<id1>", "<id2>"]}`` (or ``{"ids": "<id1>,<id2>"}``).
      Recommended for large batches as it is not constrained by URL length.

    Both forms return ``{"finished", "pending", "total", "results": [...]}``
    where ``results`` are ordered to match the input order.
    """
    ids_param = None

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, TypeError):
            return JsonResponse(
                {"task_id": None, "status": "error", "message": "Invalid JSON body"},
                status=400,
            )
        ids_param = payload.get("ids")
    else:
        ids_param = request.GET.get("ids")

    if not ids_param:
        return JsonResponse(
            {
                "task_id": None,
                "status": "error",
                "message": "Missing 'ids' parameter",
            },
            status=400,
        )

    # Normalise to a list of raw string IDs preserving input order.
    if isinstance(ids_param, (list, tuple)):
        task_ids = [str(t).strip() for t in ids_param if str(t).strip()]
    else:
        task_ids = [t.strip() for t in str(ids_param).split(",") if t.strip()]

    if len(task_ids) > MAX_BATCH_IDS:
        return JsonResponse(
            {
                "task_id": None,
                "status": "error",
                "message": "Too many ids (max %d)" % MAX_BATCH_IDS,
            },
            status=400,
        )

    # Single query for all requested tasks, replacing the previous
    # "one Task.objects.filter() per id" N+1 pattern.
    tasks_by_id = Task.objects.filter(id__in=task_ids).in_bulk()

    # Resolve eval-group ownership in bulk: collect the eval IDs referenced by
    # "eval:<id>" groups, then load those evaluations once.
    eval_ids_to_check = []
    for task in tasks_by_id.values():
        if isinstance(task.group, str) and task.group.startswith("eval:"):
            try:
                eval_ids_to_check.append(int(task.group.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass

    owned_eval_ids = set()
    if eval_ids_to_check:
        owned_eval_ids = set(
            Evaluation.objects.filter(
                id__in=eval_ids_to_check, exam__course__user=request.user
            ).values_list("id", flat=True)
        )

    # Build the owner map only for tasks with a recognised (eval:) group.
    # Tasks without a group remain public to all authenticated users (this
    # matches the original `_can_view_task` semantics).
    def _can_view_bulk(task):
        if not task.group:
            return True
        if not isinstance(task.group, str) or not task.group.startswith("eval:"):
            return False
        try:
            eval_id = int(task.group.split(":", 1)[1])
        except (ValueError, IndexError):
            return False
        return eval_id in owned_eval_ids

    finished_count = 0
    pending_count = 0
    results = []

    for task_id in task_ids:
        task = tasks_by_id.get(task_id)
        if task is not None:
            finished_count += 1
            if not _can_view_bulk(task):
                results.append({"task_id": task.id, "status": "forbidden"})
                continue

            if task.success:
                result = task.result
            elif task.result is not None:
                result = str(task.result)
            else:
                result = "Task failed"

            results.append(
                {
                    "task_id": task.id,
                    "name": task.name,
                    "status": "success" if task.success else "failed",
                    "started": task.started.isoformat() if task.started else None,
                    "stopped": task.stopped.isoformat() if task.stopped else None,
                    "result": result,
                }
            )
        else:
            pending_count += 1
            results.append({"task_id": task_id, "status": "queued"})

    return JsonResponse(
        {
            "finished": finished_count,
            "pending": pending_count,
            "total": len(task_ids),
            "results": results,
        }
    )
