"""OSSのPR検査、配布権限、main保護、二言語の入口の契約。"""
from pathlib import Path
import json
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ['Repository checks', 'Host tests', 'ESP32-S3 build', 'Dependency audit']


def load(name):
    return yaml.load((ROOT / name).read_text(), Loader=yaml.BaseLoader)


class PipelineTests(unittest.TestCase):
    def test_all_prs_and_main_run_every_required_check_without_path_filters(self):
        data = load('.github/workflows/host-tests.yml')
        self.assertIsInstance(data['on'], dict)
        self.assertIn('pull_request', data['on'])
        self.assertIn('workflow_call', data['on'])
        self.assertIn('schedule', data['on'])
        self.assertEqual(data['on']['push']['branches'], ['main'])
        for event in ('push', 'pull_request'):
            self.assertFalse(set(data['on'][event] or {}) & {'paths', 'paths-ignore'})
        self.assertEqual(sorted(j['name'] for j in data['jobs'].values()), sorted(REQUIRED))
        self.assertTrue(data['concurrency']['group'])
        for job in data['jobs'].values():
            self.assertNotIn('if', job)
            self.assertNotIn('continue-on-error', job)
            self.assertGreater(int(job['timeout-minutes']), 0)

    def test_external_actions_are_sha_pinned_and_pr_tokens_are_read_only(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            data = load(path.relative_to(ROOT))
            self.assertNotIn('pull_request_target', data['on'])
            self.assertEqual(data['permissions'], {'contents': 'read'})
            for key, job in data['jobs'].items():
                if key != 'publish':
                    self.assertNotIn('write', (job.get('permissions') or {}).values())
                for step in job.get('steps', []):
                    if 'uses' in step:
                        self.assertRegex(step['uses'], r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$')
                        if step['uses'].startswith('actions/checkout@'):
                            self.assertEqual(step['with']['persist-credentials'], 'false')
                    self.assertNotIn('continue-on-error', step)

    def test_workflow_syntax_is_checked_with_verified_actionlint(self):
        jobs = load('.github/workflows/host-tests.yml')['jobs']
        quality = next(j for j in jobs.values() if j['name'] == 'Repository checks')
        commands = '\n'.join(s.get('run', '') for s in quality['steps'])
        self.assertIn('actionlint_1.7.12_linux_amd64.tar.gz', commands)
        self.assertIn('sha256sum --check', commands)
        self.assertIn('8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8', commands)

    def test_target_is_built_and_only_text_reports_are_uploaded(self):
        jobs = load('.github/workflows/host-tests.yml')['jobs']
        target = next(j for j in jobs.values() if j['name'] == 'ESP32-S3 build')
        commands = '\n'.join(s.get('run', '') for s in target['steps'])
        self.assertIn('bootstrap.py --idf', commands)
        self.assertIn('build-candidate', commands)
        self.assertIn('size-candidate', commands)
        for job in jobs.values():
            for step in job['steps']:
                if step.get('uses', '').startswith('actions/upload-artifact@'):
                    for name in step['with']['path'].splitlines():
                        self.assertTrue(name.startswith('reports/ci/'), name)
                        self.assertTrue(name.endswith(('.txt', '.log', '.json')), name)

    def test_tag_release_rechecks_ci_before_source_only_publication(self):
        data = load('.github/workflows/release.yml')
        self.assertEqual(data['on']['push']['tags'], ['v*'])
        self.assertNotIn('pull_request', data['on'])
        self.assertEqual(data['jobs']['verify']['uses'], './.github/workflows/host-tests.yml')
        publish = data['jobs']['publish']
        self.assertEqual(publish['needs'], 'verify')
        self.assertEqual(publish['permissions'], {'contents': 'write'})
        commands = '\n'.join(s.get('run', '') for s in publish['steps'])
        self.assertIn('git merge-base --is-ancestor', commands)
        self.assertIn('tools/source_release.py', commands)
        self.assertIn('gh release create', commands)
        self.assertNotIn('--clobber', commands)
        self.assertNotIn('${{ github.ref_name }}', commands)

    def test_protection_requires_pr_and_checks_without_owner_bypass(self):
        data = json.loads((ROOT / '.github/main-protection.json').read_text())
        self.assertTrue(data['enforce_admins'])
        self.assertTrue(data['required_status_checks']['strict'])
        self.assertEqual(sorted(c['context'] for c in data['required_status_checks']['checks']), sorted(REQUIRED))
        self.assertTrue(all(c['app_id'] == 15368 for c in data['required_status_checks']['checks']))
        self.assertEqual(data['required_pull_request_reviews']['required_approving_review_count'], 0)
        self.assertTrue(data['required_conversation_resolution'])
        self.assertFalse(data['allow_force_pushes'])
        self.assertFalse(data['allow_deletions'])

    def test_dependabot_covers_both_uv_projects_and_actions(self):
        data = load('.github/dependabot.yml')
        found = {(u['package-ecosystem'], directory) for u in data['updates']
                 for directory in u.get('directories', [u.get('directory')])}
        self.assertEqual(found, {('uv', '/'), ('uv', '/firmware/esp-idf/host-tools'), ('github-actions', '/')})

    def test_readme_defaults_to_english_with_equivalent_japanese_entry(self):
        english = (ROOT / 'README.md').read_text()
        japanese = (ROOT / 'README.ja.md').read_text()
        self.assertNotRegex(re.sub(r'\[日本語\]\(README.ja.md\)', '', english), r'[ぁ-んァ-ヶ一-龯]')
        self.assertIn('[日本語](README.ja.md)', english)
        self.assertIn('[English](README.md)', japanese)
        for text in (english, japanese):
            for command in ['uv sync --locked', 'tools/bootstrap.py --font', 'tools/test.py', 'build-candidate']:
                self.assertIn(command, text)
            for link in ['docs/ci-cd.md', 'LICENSE', 'docs/validation.md']:
                self.assertIn('](' + link + ')', text)
