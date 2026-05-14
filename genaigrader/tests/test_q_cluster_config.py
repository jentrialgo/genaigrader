from django.conf import settings
from django.test import TestCase


class QClusterConfigTest(TestCase):
    def test_retry_greater_than_timeout(self):
        q_cluster = settings.Q_CLUSTER
        timeout = q_cluster["timeout"]
        retry = q_cluster["retry"]
        self.assertGreater(
            retry,
            timeout,
            f"Q_CLUSTER retry ({retry}) must be greater than timeout ({timeout}) "
            "to prevent tasks from being retriggered before completion.",
        )

    def test_required_settings_present(self):
        q_cluster = settings.Q_CLUSTER
        required_keys = [
            "name",
            "workers",
            "timeout",
            "retry",
            "queue_limit",
            "bulk",
            "orm",
        ]
        for key in required_keys:
            self.assertIn(key, q_cluster, f"Q_CLUSTER missing required key: {key}")

    def test_workers_is_positive(self):
        self.assertGreaterEqual(
            settings.Q_CLUSTER["workers"], 1, "Q_CLUSTER workers must be at least 1"
        )

    def test_orm_is_default(self):
        self.assertEqual(
            settings.Q_CLUSTER["orm"], "default", "Q_CLUSTER orm should be 'default'"
        )

    def test_ack_failures_enabled(self):
        self.assertTrue(
            settings.Q_CLUSTER.get("ack_failures", False),
            "Q_CLUSTER ack_failures should be True to clean up stale OrmQ entries",
        )

    def test_save_limit_disables_pruning(self):
        """save_limit must be 0 (no pruning): the progress bars count Task
        rows, and django-q2's default limit (250) deletes older successful
        tasks, which froze the batch progress bar at 250."""
        self.assertEqual(
            settings.Q_CLUSTER.get("save_limit"),
            0,
            "Q_CLUSTER save_limit must be 0 to disable pruning of Task records",
        )

    def test_sync_mode_is_false(self):
        """sync must be False so tasks are queued and processed by qcluster."""
        self.assertFalse(
            settings.Q_CLUSTER["sync"],
            "Q_CLUSTER sync must be False for async task execution",
        )
