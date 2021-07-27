import unittest
from unittest.mock import patch

from conventional_commits.compile_release_notes import ReleaseNoteCompiler


MOCK_GIT_LOG = """REF: Merge commit message checker modules| (HEAD -> refactor/test-release-notes-generator, origin/refactor/test-release-notes-generator)
MRG: Merge pull request #3 from octue/feature/add-other-conventional-commit-ci-components|
CHO: Remove hook installation from branch| (tag: 0.0.3, origin/main, origin/HEAD, main)
ENH: Support getting versions from poetry and npm|
FIX: Fix semantic version script; add missing config|
"""

EXPECTED_LAST_PULL_REQUEST_RELEASE_NOTES_WITH_NON_GENERATED_SECTION = "\n".join(
    [
        "BLAH BLAH BLAH",
        "<!--- START AUTOGENERATED NOTES --->",
        "## Contents",
        "",
        "### Refactoring",
        "- [x] Merge commit message checker modules",
        "",
        "<!--- END AUTOGENERATED NOTES --->",
        "YUM YUM YUM",
    ]
)


class TestReleaseNoteCompiler(unittest.TestCase):
    GIT_LOG_METHOD_PATH = "conventional_commits.compile_release_notes.ReleaseNoteCompiler._get_git_log"

    def test_unsupported_stop_point_results_in_error(self):
        """Test that using an unsupported stop point results in a ValueError."""
        with self.assertRaises(ValueError):
            ReleaseNoteCompiler(stop_point="blah")

    def test_last_release_stop_point(self):
        """Test generating release notes that stop at the last release."""
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            release_notes = ReleaseNoteCompiler(stop_point="LAST_RELEASE").compile_release_notes()

            expected = "\n".join(
                [
                    "<!--- START AUTOGENERATED NOTES --->",
                    "## Contents",
                    "",
                    "### Refactoring",
                    "- [x] Merge commit message checker modules",
                    "",
                    "### Other",
                    "- [x] Merge pull request #3 from octue/feature/add-other-conventional-commit-ci-components",
                    "",
                    "<!--- END AUTOGENERATED NOTES --->",
                ]
            )

            self.assertEqual(release_notes, expected)

    def test_last_pull_request_stop_point(self):
        """Test generating release notes that stop at the last pull request merge."""
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            release_notes = ReleaseNoteCompiler(stop_point="LAST_PULL_REQUEST").compile_release_notes()

            expected = "\n".join(
                [
                    "<!--- START AUTOGENERATED NOTES --->",
                    "## Contents",
                    "",
                    "### Refactoring",
                    "- [x] Merge commit message checker modules",
                    "",
                    "<!--- END AUTOGENERATED NOTES --->",
                ]
            )

            self.assertEqual(release_notes, expected)

    def test_with_previous_release_notes_missing_autogeneration_markers(self):
        """Test that previous release notes are not overwritten when the autogeneration markers are missing."""
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            release_notes = ReleaseNoteCompiler(
                stop_point="LAST_PULL_REQUEST", previous_notes="BLAH BLAH BLAH"
            ).compile_release_notes()

            expected = "\n".join(
                [
                    "BLAH BLAH BLAH",
                    "<!--- START AUTOGENERATED NOTES --->",
                    "## Contents",
                    "",
                    "### Refactoring",
                    "- [x] Merge commit message checker modules",
                    "",
                    "<!--- END AUTOGENERATED NOTES --->",
                ]
            )

            self.assertEqual(release_notes, expected)

    def test_with_previous_release_notes_with_empty_autogenerated_section(self):
        """Test that text outside the autogeneration markers in previous release notes is not overwritten when the
        autogenerated section is empty.
        """
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            previous_notes = (
                "BLAH BLAH BLAH\n<!--- START AUTOGENERATED NOTES --->\n<!--- END AUTOGENERATED NOTES --->YUM YUM YUM"
            )

            release_notes = ReleaseNoteCompiler(
                stop_point="LAST_PULL_REQUEST", previous_notes=previous_notes
            ).compile_release_notes()

            self.assertEqual(release_notes, EXPECTED_LAST_PULL_REQUEST_RELEASE_NOTES_WITH_NON_GENERATED_SECTION)

    def test_with_previous_release_notes_with_other_text_on_autogeneration_markers_lines(self):
        """Test that text outside but on the same line as the autogeneration markers in previous release notes is not
        overwritten when the autogenerated section is empty.
        """
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            previous_notes = (
                "BLAH BLAH BLAH<!--- START AUTOGENERATED NOTES --->\n<!--- END AUTOGENERATED NOTES --->YUM YUM YUM"
            )

            release_notes = ReleaseNoteCompiler(
                stop_point="LAST_PULL_REQUEST", previous_notes=previous_notes
            ).compile_release_notes()

            self.assertEqual(release_notes, EXPECTED_LAST_PULL_REQUEST_RELEASE_NOTES_WITH_NON_GENERATED_SECTION)

    def test_autogenerated_section_gets_overwritten(self):
        """Test that text enclosed by the autogeneration markers is overwritten."""
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            previous_notes = (
                "<!--- START AUTOGENERATED NOTES --->\nBAM BAM BAM\nWAM WAM WAM\n<!--- END AUTOGENERATED NOTES --->"
            )

            release_notes = ReleaseNoteCompiler(
                stop_point="LAST_PULL_REQUEST", previous_notes=previous_notes
            ).compile_release_notes()

            expected = "\n".join(
                [
                    "<!--- START AUTOGENERATED NOTES --->",
                    "## Contents",
                    "",
                    "### Refactoring",
                    "- [x] Merge commit message checker modules",
                    "",
                    "<!--- END AUTOGENERATED NOTES --->",
                ]
            )

            self.assertEqual(release_notes, expected)

    def test_autogenerated_section_gets_overwritten_but_text_outside_does_not(self):
        """Test that text outside a non-empty autogenerated section is not overwritten."""
        with patch(self.GIT_LOG_METHOD_PATH, return_value=MOCK_GIT_LOG):
            previous_notes = "BLAH BLAH BLAH\n<!--- START AUTOGENERATED NOTES --->\nBAM BAM BAM<!--- END AUTOGENERATED NOTES --->YUM YUM YUM"

            release_notes = ReleaseNoteCompiler(
                stop_point="LAST_PULL_REQUEST", previous_notes=previous_notes
            ).compile_release_notes()

            self.assertEqual(release_notes, EXPECTED_LAST_PULL_REQUEST_RELEASE_NOTES_WITH_NON_GENERATED_SECTION)

    def test_commit_messages_in_non_standard_format_are_left_uncategorised(self):
        """Test that commit messages in a non-standard format are put under an uncategorised heading."""
        mock_git_log = "\n".join(["This is not in the right format|", "FIX: Fix a bug|"])

        with patch(self.GIT_LOG_METHOD_PATH, return_value=mock_git_log):
            release_notes = ReleaseNoteCompiler(stop_point="LAST_PULL_REQUEST").compile_release_notes()

        expected = "\n".join(
            [
                "<!--- START AUTOGENERATED NOTES --->",
                "## Contents",
                "",
                "### Fixes",
                "- [x] Fix a bug",
                "",
                "### Uncategorised!",
                "- [x] This is not in the right format",
                "",
                "<!--- END AUTOGENERATED NOTES --->",
            ]
        )

        self.assertEqual(release_notes, expected)

    def test_commit_messages_with_unrecognised_commit_codes_are_categorised_as_other(self):
        """Test that commit messages with an unrecognised commit code are categorised under "other"."""
        mock_git_log = "\n".join(["BAM: An unrecognised commit code|", "FIX: Fix a bug|"])

        with patch(self.GIT_LOG_METHOD_PATH, return_value=mock_git_log):
            release_notes = ReleaseNoteCompiler(stop_point="LAST_PULL_REQUEST").compile_release_notes()

        expected = "\n".join(
            [
                "<!--- START AUTOGENERATED NOTES --->",
                "## Contents",
                "",
                "### Fixes",
                "- [x] Fix a bug",
                "",
                "### Other",
                "- [x] An unrecognised commit code",
                "",
                "<!--- END AUTOGENERATED NOTES --->",
            ]
        )

        self.assertEqual(release_notes, expected)
