function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function pollTask(taskId, callback, interval) {
    interval = interval || 2000;
    var MAX_RETRIES = 10;
    var MAX_INTERVAL = 30000;
    var retries = 0;
    var id;
    function check() {
        fetch('/task/' + taskId + '/')
            .then(function(r) {
                var ct = r.headers.get("content-type") || "";
                if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
                    throw new Error("Invalid response or session expired");
                }
                return r.json();
            })
            .then(function(data) {
                retries = 0;
                if (data.status === 'success' || data.status === 'failed') {
                    callback(data.status, data.result);
                } else {
                    id = setTimeout(check, interval);
                }
            })
            .catch(function(e) {
                retries++;
                if (retries >= MAX_RETRIES) return;
                var backoff = Math.min(interval * Math.pow(2, retries - 1), MAX_INTERVAL);
                id = setTimeout(check, backoff);
            });
    }
    id = setTimeout(check, 0);
    return {
        stop: function() { clearTimeout(id); }
    };
}

function pollBatchTasks(taskIds, onProgress, onComplete, interval) {
    interval = interval || 2000;
    var MAX_RETRIES = 10;
    var MAX_INTERVAL = 30000;
    var retries = 0;
    var id;
    function check() {
        fetch("/batch-task-status/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: JSON.stringify({ ids: taskIds })
        })
            .then(function(r) {
                var ct = r.headers.get("content-type") || "";
                if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
                    if (r.status === 400) {
                        // Hard error (e.g. too many ids) — do not retry forever.
                        if (onComplete) onComplete([]);
                        return null;
                    }
                    throw new Error("Invalid response or session expired");
                }
                return r.json();
            })
            .then(function(data) {
                if (!data) return;
                if (data.status === "error") {
                    if (onComplete) onComplete([]);
                    return;
                }
                retries = 0;
                onProgress(data.finished, data.total, data.results, data.pending || 0);
                if (data.finished >= data.total) {
                    onComplete(data.results);
                } else {
                    id = setTimeout(check, interval);
                }
            })
            .catch(function(e) {
                retries++;
                if (retries >= MAX_RETRIES) {
                    if (onComplete) onComplete([]);
                    return;
                }
                var backoff = Math.min(interval * Math.pow(2, retries - 1), MAX_INTERVAL);
                id = setTimeout(check, backoff);
            });
    }
    id = setTimeout(check, 0);
    return {
        stop: function() { clearTimeout(id); }
    };
}
