"""Sharing and cloud catch-up use disposable repositories, never the owner's checkout."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import sync_kenn_app, sync_local_checkout


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.remote = self.root / "sharing.git"
        self.seed = self.root / "seed"
        for repo in (self.source, self.seed):
            repo.mkdir()
            self.run_git(repo, "init", "-b", "main")
            self.run_git(repo, "config", "user.name", "KENN sync tests")
            self.run_git(repo, "config", "user.email", "tests@example.com")
        self.run_git(self.root, "init", "--bare", str(self.remote))
        self.commit_file(self.seed, "old.txt", "Standalone history")
        self.run_git(self.seed, "push", str(self.remote), "HEAD:refs/heads/main")
        self.original_main = self.run_git(self.seed, "rev-parse", "HEAD")
        self.commit_file(self.source, "products/kenn/answer.py", "answer = 1\n")
        self.commit_file(self.source, "products/other/private.txt", "Other product")
        self.run_git(self.source, "switch", "-c", "fix/kenn")
        self.cwd = Path.cwd()
        os.chdir(self.source)
        self.addCleanup(os.chdir, self.cwd)

    def run_git(self, repo, *args, input=None):
        return subprocess.run(["git", "-C", str(repo), *args], input=input, text=True,
                              capture_output=True, check=True).stdout.strip()

    def commit_file(self, repo, name, text):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.run_git(repo, "add", "--", name)
        self.run_git(repo, "commit", "-m", "Change fixture")

    def args(self, **overrides):
        values = dict(source_ref="HEAD", branch="fix/kenn", remote=str(self.remote),
                      base_branch="main", destination_branch=None, bootstrap=True,
                      reconcile=False, push=True)
        return argparse.Namespace(**{**values, **overrides})

    def sync(self, **overrides):
        with contextlib.redirect_stdout(io.StringIO()):
            return sync_kenn_app.synchronize(self.args(**overrides))

    def remote_ref(self, branch):
        return self.run_git(self.root, "--git-dir", str(self.remote), "rev-parse", f"refs/heads/{branch}")

    def tree(self, ref):
        return self.run_git(self.source, "rev-parse", f"{ref}^{{tree}}")


class SharingSyncTests(RepositoryFixture):
    def test_new_feature_branch_exports_only_committed_kenn_and_preserves_main(self):
        (self.source / "products/kenn/answer.py").write_text("Uncommitted change")
        (self.source / "products/kenn/private.wav").write_bytes(b"local only")
        commit = self.sync()
        self.assertEqual(self.tree(commit), self.run_git(self.source, "rev-parse", "HEAD:products/kenn"))
        self.assertEqual(self.run_git(self.source, "ls-tree", "--name-only", commit), "answer.py")
        self.assertEqual(self.run_git(self.source, "rev-parse", f"{commit}^"), self.original_main)
        self.assertEqual(self.remote_ref("main"), self.original_main)
        self.assertEqual((self.source / "products/kenn/answer.py").read_text(), "Uncommitted change")

    def test_next_source_commit_fast_forwards_the_matching_sharing_branch(self):
        first = self.sync()
        self.commit_file(self.source, "products/kenn/answer.py", "answer = 2\n")
        second = self.sync()
        self.assertEqual(self.run_git(self.source, "rev-parse", f"{second}^"), first)
        self.assertEqual(self.remote_ref("fix/kenn"), second)
        self.assertEqual(self.remote_ref("main"), self.original_main)

    def test_unchanged_kenn_tree_does_not_create_another_mirror_commit(self):
        first = self.sync()
        self.commit_file(self.source, "products/other/private.txt", "Unrelated update")
        self.assertEqual(self.sync(), first)

    def test_independent_colleague_edits_stop_the_mirror(self):
        # A colleague's destination edit must survive even when the source advances.
        first = self.sync()
        tree = self.run_git(self.seed, "rev-parse", "HEAD^{tree}")
        self.run_git(self.source, "fetch", str(self.remote), "main")
        edited = self.run_git(self.source, "commit-tree", tree, "-p", first, input="Colleague edit\n")
        self.run_git(self.source, "push", str(self.remote), f"{edited}:refs/heads/fix/kenn")
        self.commit_file(self.source, "products/kenn/answer.py", "answer = 2\n")
        with self.assertRaisesRegex(RuntimeError, "independent edits"):
            self.sync()
        self.assertEqual(self.remote_ref("fix/kenn"), edited)

    def test_unmarked_existing_branch_requires_reconciliation(self):
        self.run_git(self.seed, "push", str(self.remote), "HEAD:refs/heads/fix/kenn")
        with self.assertRaisesRegex(RuntimeError, "reconciliation PR"):
            self.sync()

    def test_rewritten_source_history_stops_the_mirror(self):
        self.sync()
        tree = self.run_git(self.source, "rev-parse", "HEAD^{tree}")
        rewritten = self.run_git(self.source, "commit-tree", tree, input="New unrelated history\n")
        with self.assertRaisesRegex(RuntimeError, "rewritten"):
            self.sync(source_ref=rewritten)

    def test_main_is_established_by_a_review_branch_and_its_merge(self):
        with self.assertRaisesRegex(RuntimeError, "reconciliation PR"):
            self.sync(branch="main")
        review = self.sync(branch="main", destination_branch="sync/reconcile", reconcile=True)
        self.assertEqual(self.remote_ref("main"), self.original_main)
        # A normal PR merge retains the source marker through its second parent.
        merged = self.run_git(self.source, "commit-tree", self.tree(review), "-p", self.original_main,
                              "-p", review, input="Merge reviewed baseline\n")
        self.run_git(self.source, "push", str(self.remote), f"{merged}:refs/heads/main")
        self.commit_file(self.source, "products/kenn/answer.py", "answer = 2\n")
        update = self.sync(branch="main")
        self.assertEqual(self.run_git(self.source, "rev-parse", f"{update}^"), merged)

    def test_reconciliation_cannot_replace_an_existing_review_branch(self):
        self.sync(branch="main", destination_branch="sync/reconcile", reconcile=True)
        with self.assertRaisesRegex(RuntimeError, "new review branch"):
            self.sync(branch="main", destination_branch="sync/reconcile", reconcile=True)

    def test_dry_run_prepares_a_commit_without_publishing_it(self):
        self.sync(push=False)
        self.assertEqual(self.run_git(self.source, "ls-remote", "--heads", str(self.remote), "refs/heads/fix/kenn"), "")

    def test_a_different_branch_mapping_requires_explicit_reconciliation(self):
        with self.assertRaisesRegex(RuntimeError, "different destination branch"):
            self.sync(destination_branch="other")

    def assert_export_blocked(self, name, content):
        self.commit_file(self.source, f"products/kenn/{name}", content)
        with self.assertRaisesRegex(RuntimeError, "Export blocked"):
            self.sync()

    def test_committed_private_audio_blocks_publication(self):
        self.assert_export_blocked("clip.wav", "audio")

    def test_committed_runtime_data_blocks_publication(self):
        self.assert_export_blocked("runtime/log.txt", "session")

    def test_committed_model_weights_block_publication(self):
        self.assert_export_blocked("model.gguf", "weights")

    def test_committed_credentials_block_publication(self):
        self.assert_export_blocked("secret.txt", "gh" + "p_" + "x" * 36)

    def test_assistant_task_identifiers_are_not_mistaken_for_credentials(self):
        self.commit_file(self.source, "products/kenn/receipt.json", '"task-' + 'a' * 32 + '"')
        self.sync()

    def test_committed_personal_paths_block_publication(self):
        self.assert_export_blocked("handoff.md", "/Users/" + "local-owner/project")

    def test_relative_in_tree_symlinks_are_exportable(self):
        (self.source / "products/kenn/source").symlink_to("answer.py")
        self.run_git(self.source, "add", "--", "products/kenn/source")
        self.run_git(self.source, "commit", "-m", "Add fixture link")
        self.sync()

    def test_escaping_symlinks_block_publication(self):
        (self.source / "products/kenn/source").symlink_to("../../private")
        self.run_git(self.source, "add", "--", "products/kenn/source")
        self.run_git(self.source, "commit", "-m", "Add escaping fixture link")
        with self.assertRaisesRegex(RuntimeError, "Export blocked"):
            self.sync()


class LocalCatchUpTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.run_git(self.source, "remote", "add", "origin", str(self.remote))
        self.run_git(self.source, "push", "-u", "origin", "HEAD:refs/heads/fix/kenn")
        self.cloud = self.root / "cloud"
        self.run_git(self.root, "clone", "--branch", "fix/kenn", str(self.remote), str(self.cloud))
        self.run_git(self.cloud, "config", "user.name", "Cloud fixture")
        self.run_git(self.cloud, "config", "user.email", "tests@example.com")
        self.commit_file(self.cloud, "products/kenn/answer.py", "Cloud update\n")
        self.run_git(self.cloud, "push", "origin", "HEAD")

    def test_clean_checkout_fast_forwards_to_pushed_cloud_work(self):
        self.assertIn("Updated fix/kenn", sync_local_checkout.synchronize(self.source))
        self.assertEqual((self.source / "products/kenn/answer.py").read_text(), "Cloud update\n")

    def test_dirty_local_files_are_preserved_while_cloud_work_is_fetched(self):
        # Fetching cloud work must never replace the owner's unfinished local edit.
        path = self.source / "products/kenn/answer.py"
        path.write_text("Local unfinished work\n")
        head = self.run_git(self.source, "rev-parse", "HEAD")
        self.assertIn("local files", sync_local_checkout.synchronize(self.source))
        self.assertEqual(path.read_text(), "Local unfinished work\n")
        self.assertEqual(self.run_git(self.source, "rev-parse", "HEAD"), head)
        self.assertEqual(self.run_git(self.source, "rev-parse", "origin/fix/kenn"), self.run_git(self.cloud, "rev-parse", "HEAD"))

    def test_untracked_local_files_pause_the_pull(self):
        (self.source / "untracked.txt").write_text("Keep this")
        self.assertIn("local files", sync_local_checkout.synchronize(self.source))
        self.assertEqual((self.source / "untracked.txt").read_text(), "Keep this")

    def test_local_commits_are_not_reset_or_automatically_merged(self):
        self.commit_file(self.source, "local.txt", "Local commit")
        head = self.run_git(self.source, "rev-parse", "HEAD")
        self.assertIn("local commits need review", sync_local_checkout.synchronize(self.source))
        self.assertEqual(self.run_git(self.source, "rev-parse", "HEAD"), head)

    def test_missing_external_drive_is_a_pause(self):
        self.assertIn("drive is unavailable", sync_local_checkout.synchronize(self.root / "missing"))


class LocalInstallerTests(unittest.TestCase):
    def test_installer_registers_only_the_owner_sync_agent_with_a_stable_script(self):
        from scripts import install_local_sync
        import plistlib
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with patch.object(install_local_sync.Path, "home", return_value=home), \
                 patch.object(install_local_sync.sys, "argv", ["installer", "--repo", folder]), \
                 patch.object(install_local_sync.subprocess, "run") as run:
                run.return_value.returncode = 1
                with contextlib.redirect_stdout(io.StringIO()):
                    install_local_sync.main()
            agent = home / "Library/LaunchAgents/com.nitedsp.kenn-git-catchup.plist"
            config = plistlib.loads(agent.read_bytes())
            self.assertEqual(config["StartInterval"], 300)
            self.assertTrue(config["RunAtLoad"])
            self.assertEqual(config["ProgramArguments"][3], str(home.resolve()))
            self.assertTrue(Path(config["ProgramArguments"][1]).is_file())
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([cmd[1] for cmd in commands], ["print", "-lint", "bootstrap"])



if __name__ == "__main__":
    unittest.main()
