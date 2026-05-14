(function() {
    "use strict";

    // --------------------------------------------------------------------------
    // Constants
    // --------------------------------------------------------------------------
    var STORAGE_KEY_EVALS = "genaigrader_pending_evaluations";
    var STORAGE_KEY_DLS = "genaigrader_pending_downloads";
    var MAX_TOASTS = 3;
    var TOAST_AUTO_DISMISS_MS = 8000;

    // A single batch poll is fired every POLL_INTERVAL_MS for all pending
    // evaluations/downloads combined into one request. Replaces the previous
    // design which created one setInterval() per pending item (which caused
    // an unbounded number of HTTP requests every 3 s when many evaluations
    // were queued).
    var POLL_INTERVAL_MS = 5000;
    var POLL_MAX_INTERVAL_MS = 30000;     // backoff cap after errors
    var POLL_MAX_RETRIES = 10;            // hard stop after this many failures

    var STORAGE_RESCAN_MS = 15000;        // how often localStorage is re-read
    var MAX_AGE_MS = 4 * 60 * 60 * 1000;  // drop stale entries after 4 h
    var CONTAINER_ID = "toast-container";

    // --------------------------------------------------------------------------
    // State
    // --------------------------------------------------------------------------
    // Two independent recursive setTimeout() loops, one for evaluations and
    // one for downloads. Each iteration issues a single batch request.
    var evalTimer = null;
    var evalRetries = 0;
    var dlTimer = null;
    var dlRetries = 0;
    var displayedToasts = {}; // key -> true (prevents duplicate DOM toasts)

    // --------------------------------------------------------------------------
    // Cookie helper (kept local so notifications.js does not depend on
    // polling.js being loaded first).
    // --------------------------------------------------------------------------
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            var cookies = document.cookie.split(";");
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + "=")) {
                    cookieValue = decodeURIComponent(
                        cookie.substring(name.length + 1)
                    );
                    break;
                }
            }
        }
        return cookieValue;
    }

    // --------------------------------------------------------------------------
    // Storage helpers
    // --------------------------------------------------------------------------
    function readPending(key) {
        try {
            var raw = localStorage.getItem(key);
            if (!raw) return [];
            var items = JSON.parse(raw);
            if (!Array.isArray(items)) return [];
            return items;
        } catch (e) {
            return [];
        }
    }

    function writePending(key, items) {
        try {
            localStorage.setItem(key, JSON.stringify(items));
        } catch (e) {
            // ignore (e.g. storage full)
        }
    }

    function addPending(key, item) {
        var items = readPending(key);
        // Avoid exact duplicates
        var exists = items.some(function(it) {
            return (item.evalId !== undefined && it.evalId === item.evalId) ||
                   (item.taskId !== undefined && it.taskId === item.taskId);
        });
        if (!exists) {
            items.push(item);
            writePending(key, items);
        }
    }

    function removePending(key, predicate) {
        var items = readPending(key);
        var next = items.filter(function(it) {
            return !predicate(it);
        });
        writePending(key, next);
    }

    // --------------------------------------------------------------------------
    // Toast UI
    // --------------------------------------------------------------------------
    function getContainer() {
        var el = document.getElementById(CONTAINER_ID);
        if (!el) {
            el = document.createElement("div");
            el.id = CONTAINER_ID;
            el.className = "toast-container";
            document.body.appendChild(el);
        }
        return el;
    }

    function pruneToasts() {
        var container = getContainer();
        var toasts = container.querySelectorAll(".toast");
        if (toasts.length > MAX_TOASTS) {
            // Remove oldest (first in DOM order)
            var excess = toasts.length - MAX_TOASTS;
            for (var i = 0; i < excess; i++) {
                var old = toasts[i];
                if (old) {
                    removeToast(old);
                }
            }
        }
    }

    function removeToast(el) {
        if (!el) return;
        el.classList.remove("toast-slide-in");
        el.classList.add("toast-slide-out");
        setTimeout(function() {
            if (el.parentNode) {
                el.parentNode.removeChild(el);
            }
        }, 300);
    }

    function showToast(message, type, relatedUrl, key) {
        if (displayedToasts[key]) return;
        displayedToasts[key] = true;

        var container = getContainer();
        var el = document.createElement("div");
        el.className = "toast toast-slide-in toast-" + (type || "info");
        el.setAttribute("role", "alert");
        el.setAttribute("aria-live", "polite");

        var body = document.createElement("div");
        body.className = "toast-body";
        body.textContent = message;

        var closeBtn = document.createElement("button");
        closeBtn.className = "toast-close";
        closeBtn.innerHTML = "&times;";
        closeBtn.setAttribute("aria-label", "Dismiss notification");
        closeBtn.onclick = function() {
            removeToast(el);
            delete displayedToasts[key];
        };

        el.appendChild(body);
        el.appendChild(closeBtn);

        if (relatedUrl) {
            el.classList.add("toast-clickable");
            el.addEventListener("click", function(evt) {
                if (evt.target === closeBtn || closeBtn.contains(evt.target)) {
                    return;
                }
                window.location.href = relatedUrl;
            });
        }

        container.appendChild(el);
        pruneToasts();

        // Auto-dismiss
        setTimeout(function() {
            removeToast(el);
            delete displayedToasts[key];
        }, TOAST_AUTO_DISMISS_MS);
    }

    // --------------------------------------------------------------------------
    // Age-based cleanup
    // --------------------------------------------------------------------------
    // Drops entries older than MAX_AGE_MS. Returns the surviving, actionable
    // items (those with a usable identifier). Also persists the cleaned list.
    function purgeStaleEvaluations() {
        var now = Date.now();
        var cutoff = now - MAX_AGE_MS;
        var items = readPending(STORAGE_KEY_EVALS);
        var kept = [];
        for (var i = 0; i < items.length; i++) {
            var ev = items[i];
            if (!ev || !ev.evalId) continue;
            if (ev.addedAt && ev.addedAt < cutoff) continue; // too old
            kept.push(ev);
        }
        writePending(STORAGE_KEY_EVALS, kept);
        return kept;
    }

    function purgeStaleDownloads() {
        var now = Date.now();
        var cutoff = now - MAX_AGE_MS;
        var items = readPending(STORAGE_KEY_DLS);
        var kept = [];
        for (var i = 0; i < items.length; i++) {
            var dl = items[i];
            if (!dl || !dl.taskId) continue;
            if (dl.addedAt && dl.addedAt < cutoff) continue; // too old
            kept.push(dl);
        }
        writePending(STORAGE_KEY_DLS, kept);
        return kept;
    }

    // --------------------------------------------------------------------------
    // Batch polling: evaluations
    // --------------------------------------------------------------------------
    // One POST /batch-evaluation-status/ carries every pending evaluation ID
    // (regardless of count) in the JSON body. The server caps at MAX_BATCH_IDS
    // and returns one row per ID preserving the input order.
    function pollEvaluationsBatch() {
        var items = purgeStaleEvaluations();
        if (!items.length) {
            // Nothing to poll: stop the loop. scanAndRestart() (and
            // addPendingEvaluation) will restart it when new items appear.
            evalRetries = 0;
            evalTimer = null;
            return;
        }

        // Build id -> metadata map for the response handling below.
        var ids = [];
        var metaById = {};
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            ids.push(it.evalId);
            // Use a String key so lookups match the (possibly numeric) ids
            // returned in the JSON response.
            metaById["" + it.evalId] = it;
        }

        fetch("/batch-evaluation-status/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify({ ids: ids }),
        })
            .then(function(r) {
                var ct = r.headers.get("content-type") || "";
                if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
                    // A redirect (e.g. to the login page) means the session
                    // expired; keep retrying slowly rather than hammering.
                    throw new Error("Invalid response or session expired");
                }
                return r.json();
            })
            .then(function(data) {
                if (!data || data.status === "error" || !data.results) {
                    // Soft server error — schedule next cycle without blowing
                    // away the pending list.
                    scheduleEvalWithBackoff();
                    return;
                }
                evalRetries = 0;

                for (var k = 0; k < data.results.length; k++) {
                    var ev = data.results[k];
                    var key = "eval_" + ev.evaluation_id;

                    if (ev.status === "completed") {
                        removePending(STORAGE_KEY_EVALS, function(it) {
                            return String(it.evalId) === String(ev.evaluation_id);
                        });
                        var meta = metaById["" + ev.evaluation_id] || {};
                        var gradeStr = ev.grade !== null && ev.grade !== undefined
                            ? String(ev.grade) : "N/A";
                        showToast(
                            "Evaluation completed — Grade: " + gradeStr,
                            "success",
                            "/exam/" + meta.examId + "/?eval_id=" + ev.evaluation_id,
                            key
                        );
                    } else if (ev.status === "failed") {
                        removePending(STORAGE_KEY_EVALS, function(it) {
                            return String(it.evalId) === String(ev.evaluation_id);
                        });
                        var metaF = metaById["" + ev.evaluation_id] || {};
                        var reason = ev.failed_reason || "Unknown error";
                        showToast(
                            "Evaluation failed: " + reason,
                            "error",
                            "/exam/" + metaF.examId + "/?eval_id=" + ev.evaluation_id,
                            key
                        );
                    } else if (ev.status === "not_found") {
                        // The evaluation no longer exists (deleted, wrong ID,
                        // or not owned by this user). Drop it so we do not
                        // poll it forever.
                        removePending(STORAGE_KEY_EVALS, function(it) {
                            return String(it.evalId) === String(ev.evaluation_id);
                        });
                    }
                    // pending / running: keep polling on the next cycle
                }

                evalTimer = setTimeout(pollEvaluationsBatch, POLL_INTERVAL_MS);
            })
            .catch(function() {
                scheduleEvalWithBackoff();
            });
    }

    function scheduleEvalWithBackoff() {
        evalRetries++;
        if (evalRetries >= POLL_MAX_RETRIES) {
            // Stop the loop; a future storage rescan can restart it if the
            // session recovers (e.g. after the user re-logs in on this page).
            evalRetries = 0;
            evalTimer = null;
            return;
        }
        var backoff = Math.min(
            POLL_INTERVAL_MS * Math.pow(2, evalRetries - 1),
            POLL_MAX_INTERVAL_MS
        );
        evalTimer = setTimeout(pollEvaluationsBatch, backoff);
    }

    // --------------------------------------------------------------------------
    // Batch polling: downloads
    // --------------------------------------------------------------------------
    // One POST /batch-task-status/ carries every pending download task ID in
    // the JSON body. Mirrors pollEvaluationsBatch().
    function pollDownloadsBatch() {
        var items = purgeStaleDownloads();
        if (!items.length) {
            // Nothing to poll: stop the loop. scanAndRestart() (and
            // addPendingDownload) will restart it when new items appear.
            dlRetries = 0;
            dlTimer = null;
            return;
        }

        var ids = [];
        var metaById = {};
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            ids.push(it.taskId);
            metaById["" + it.taskId] = it;
        }

        fetch("/batch-task-status/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify({ ids: ids }),
        })
            .then(function(r) {
                var ct = r.headers.get("content-type") || "";
                if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
                    throw new Error("Invalid response or session expired");
                }
                return r.json();
            })
            .then(function(data) {
                if (!data || data.status === "error" || !data.results) {
                    scheduleDlWithBackoff();
                    return;
                }
                dlRetries = 0;

                for (var k = 0; k < data.results.length; k++) {
                    var task = data.results[k];
                    var key = "dl_" + task.task_id;

                    if (task.status === "success") {
                        removePending(STORAGE_KEY_DLS, function(it) {
                            return String(it.taskId) === String(task.task_id);
                        });
                        var metaOk = metaById["" + task.task_id] || {};
                        var nameOk = metaOk.modelName || "Model";
                        showToast(
                            nameOk + " downloaded successfully",
                            "success",
                            "/api/",
                            key
                        );
                    } else if (task.status === "failed") {
                        removePending(STORAGE_KEY_DLS, function(it) {
                            return String(it.taskId) === String(task.task_id);
                        });
                        var metaF = metaById["" + task.task_id] || {};
                        var nameF = metaF.modelName || "Model";
                        var result = task.result || "Unknown error";
                        showToast(
                            nameF + " download failed: " + result,
                            "error",
                            null,
                            key
                        );
                    } else if (task.status === "forbidden") {
                        // Not authorised to view this task — drop it.
                        removePending(STORAGE_KEY_DLS, function(it) {
                            return String(it.taskId) === String(task.task_id);
                        });
                    }
                    // queued: keep polling on the next cycle
                }

                dlTimer = setTimeout(pollDownloadsBatch, POLL_INTERVAL_MS);
            })
            .catch(function() {
                scheduleDlWithBackoff();
            });
    }

    function scheduleDlWithBackoff() {
        dlRetries++;
        if (dlRetries >= POLL_MAX_RETRIES) {
            dlRetries = 0;
            dlTimer = null;
            return;
        }
        var backoff = Math.min(
            POLL_INTERVAL_MS * Math.pow(2, dlRetries - 1),
            POLL_MAX_INTERVAL_MS
        );
        dlTimer = setTimeout(pollDownloadsBatch, backoff);
    }

    // --------------------------------------------------------------------------
    // (Re)starter: re-reads localStorage periodically and restarts a stopped
    // loop if new pending items appear (e.g. added from another tab, or after
    // a backoff gave up).
    // --------------------------------------------------------------------------
    function scanAndRestart() {
        var evals = readPending(STORAGE_KEY_EVALS);
        var dls = readPending(STORAGE_KEY_DLS);

        if (evals.length && evalTimer === null) {
            evalRetries = 0;
            evalTimer = setTimeout(pollEvaluationsBatch, 0);
        }

        if (dls.length && dlTimer === null) {
            dlRetries = 0;
            dlTimer = setTimeout(pollDownloadsBatch, 0);
        }
    }

    // --------------------------------------------------------------------------
    // Public API
    // --------------------------------------------------------------------------
    // Kept identical to the previous version so existing call sites
    // (evaluate.js, batch_evaluations.js, api.js) keep working unchanged.
    // addPendingEvaluation / addPendingDownload store the item in localStorage;
    // the single batch loop picks it up on its next tick. If the loop is idle
    // (no pending items) we kick it off immediately so the new item is noticed
    // without waiting for the next STORAGE_RESCAN_MS window.
    window.addPendingEvaluation = function(evalId, examId) {
        if (!evalId) return;
        addPending(STORAGE_KEY_EVALS, {
            evalId: evalId,
            examId: examId,
            addedAt: Date.now(),
        });
        if (evalTimer === null) {
            evalRetries = 0;
            evalTimer = setTimeout(pollEvaluationsBatch, 0);
        }
    };

    window.addPendingDownload = function(taskId, modelName) {
        if (!taskId) return;
        addPending(STORAGE_KEY_DLS, {
            taskId: taskId,
            modelName: modelName,
            addedAt: Date.now(),
        });
        if (dlTimer === null) {
            dlRetries = 0;
            dlTimer = setTimeout(pollDownloadsBatch, 0);
        }
    };

    // --------------------------------------------------------------------------
    // Init
    // --------------------------------------------------------------------------
    function start() {
        // Kick off both loops immediately for pending items already in storage
        // (e.g. page reload while evaluations are still running). scanAndRestart
        // re-checks periodically and restarts any loop that stopped because of
        // repeated errors or a transient empty pending list.
        scanAndRestart();
        setInterval(scanAndRestart, STORAGE_RESCAN_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();