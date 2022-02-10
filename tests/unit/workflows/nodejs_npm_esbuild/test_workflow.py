from unittest import TestCase
from mock import patch, call

from aws_lambda_builders.actions import CopySourceAction
from aws_lambda_builders.exceptions import WorkflowFailedError
from aws_lambda_builders.architecture import ARM64
from aws_lambda_builders.workflows.nodejs_npm.actions import NodejsNpmInstallAction, NodejsNpmCIAction
from aws_lambda_builders.workflows.nodejs_npm_esbuild import NodejsNpmEsbuildWorkflow
from aws_lambda_builders.workflows.nodejs_npm_esbuild.actions import EsbuildBundleAction
from aws_lambda_builders.workflows.nodejs_npm_esbuild.esbuild import SubprocessEsbuild
from aws_lambda_builders.workflows.nodejs_npm_esbuild.utils import EXPERIMENTAL_FLAG_ESBUILD


class FakePopen:
    def __init__(self, out=b"out", err=b"err", retcode=0):
        self.out = out
        self.err = err
        self.returncode = retcode

    def communicate(self):
        return self.out, self.err


class TestNodejsNpmEsbuildWorkflow(TestCase):

    """
    the workflow requires an external utility (npm) to run, so it is extensively tested in integration tests.
    this is just a quick wiring test to provide fast feedback if things are badly broken
    """

    @patch("aws_lambda_builders.workflows.nodejs_npm.utils.OSUtils")
    def setUp(self, OSUtilMock):
        self.osutils = OSUtilMock.return_value
        self.osutils.pipe = "PIPE"
        self.popen = FakePopen()
        self.osutils.popen.side_effect = [self.popen]
        self.osutils.is_windows.side_effect = [False]
        self.osutils.joinpath.side_effect = lambda a, b: "{}/{}".format(a, b)

    def test_workflow_sets_up_npm_actions_with_bundler_if_manifest_requests_it(self):

        self.osutils.parse_json.side_effect = [{"aws_sam": {"bundler": "esbuild"}}]
        self.osutils.file_exists.side_effect = [True, False, False]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch_dir",
            "manifest",
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.assertEqual(len(workflow.actions), 3)
        self.assertIsInstance(workflow.actions[0], CopySourceAction)
        self.assertIsInstance(workflow.actions[1], NodejsNpmInstallAction)
        self.assertIsInstance(workflow.actions[2], EsbuildBundleAction)
        self.osutils.file_exists.assert_has_calls(
            [call("source/package-lock.json"), call("source/npm-shrinkwrap.json")]
        )

    def test_sets_up_esbuild_search_path_from_npm_bin(self):

        self.popen.out = b"project/bin"
        self.osutils.parse_json.side_effect = [{"aws_sam": {"bundler": "esbuild"}}]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch_dir",
            "manifest",
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.osutils.popen.assert_called_with(["npm", "bin"], stdout="PIPE", stderr="PIPE", cwd="scratch_dir")
        esbuild = workflow.actions[2].subprocess_esbuild

        self.assertIsInstance(esbuild, SubprocessEsbuild)
        self.assertEqual(esbuild.executable_search_paths, ["project/bin"])

    def test_sets_up_esbuild_search_path_with_workflow_executable_search_paths_after_npm_bin(self):

        self.popen.out = b"project/bin"
        self.osutils.parse_json.side_effect = [{"aws_sam": {"bundler": "esbuild"}}]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch_dir",
            "manifest",
            osutils=self.osutils,
            executable_search_paths=["other/bin"],
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.osutils.popen.assert_called_with(["npm", "bin"], stdout="PIPE", stderr="PIPE", cwd="scratch_dir")
        esbuild = workflow.actions[2].subprocess_esbuild
        self.assertIsInstance(esbuild, SubprocessEsbuild)
        self.assertEqual(esbuild.executable_search_paths, ["project/bin", "other/bin"])

    def test_workflow_uses_npm_ci_if_lockfile_exists(self):

        self.osutils.parse_json.side_effect = [{"aws_sam": {"bundler": "esbuild"}}]
        self.osutils.file_exists.side_effect = [True, True]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch_dir",
            "manifest",
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.assertEqual(len(workflow.actions), 3)
        self.assertIsInstance(workflow.actions[0], CopySourceAction)
        self.assertIsInstance(workflow.actions[1], NodejsNpmCIAction)
        self.assertIsInstance(workflow.actions[2], EsbuildBundleAction)
        self.osutils.file_exists.assert_has_calls([call("source/package-lock.json")])

    def test_workflow_uses_npm_ci_if_shrinkwrap_exists(self):

        self.osutils.parse_json.side_effect = [{"aws_sam": {"bundler": "esbuild"}}]
        self.osutils.file_exists.side_effect = [True, False, True]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch_dir",
            "manifest",
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.assertEqual(len(workflow.actions), 3)
        self.assertIsInstance(workflow.actions[0], CopySourceAction)
        self.assertIsInstance(workflow.actions[1], NodejsNpmCIAction)
        self.assertIsInstance(workflow.actions[2], EsbuildBundleAction)
        self.osutils.file_exists.assert_has_calls(
            [call("source/package-lock.json"), call("source/npm-shrinkwrap.json")]
        )

    def test_must_validate_architecture(self):
        self.osutils.is_windows.side_effect = [False, False]
        self.osutils.popen.side_effect = [self.popen, self.popen]

        workflow = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch",
            "manifest",
            options={"artifact_executable_name": "foo"},
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        workflow_with_arm = NodejsNpmEsbuildWorkflow(
            "source",
            "artifacts",
            "scratch",
            "manifest",
            architecture=ARM64,
            osutils=self.osutils,
            experimental_flags=[EXPERIMENTAL_FLAG_ESBUILD],
        )

        self.assertEqual(workflow.architecture, "x86_64")
        self.assertEqual(workflow_with_arm.architecture, "arm64")