import unittest

from configure_source_automation import migration_triggered


class ComponentAutomationTest(unittest.TestCase):
    def run_record(self, event, actor='maintainer', branch='OpenHarmony-7.0-Release-qemu'):
        return dict(event=event, actor={'login': actor}, head_branch=branch)

    def test_preserves_manual_runs_and_unrelated_human_pushes(self):
        self.assertFalse(migration_triggered(self.run_record('workflow_dispatch'), 'maintainer'))
        self.assertFalse(migration_triggered(self.run_record('push', branch='unrelated-work'), 'maintainer'))
        self.assertFalse(migration_triggered(self.run_record('push', actor='another-maintainer'), 'maintainer'))
        self.assertTrue(migration_triggered(self.run_record('push'), 'maintainer'))

    def test_identifies_automatic_mirror_and_dependency_workflows(self):
        self.assertTrue(migration_triggered(self.run_record('push',
            actor='openharmony-qemu-mirror-sync[bot]', branch='master'), 'maintainer'))
        for event in ('push', 'pull_request', 'pull_request_target'):
            self.assertTrue(migration_triggered(self.run_record(event,
                actor='dependabot[bot]', branch='dependabot/github_actions/update'), 'maintainer'))


if __name__ == '__main__':
    unittest.main()
