import re
import subprocess
import sys
import requests


LAST_RELEASE = "LAST_RELEASE"
LAST_PULL_REQUEST = "LAST_PULL_REQUEST"

SEMANTIC_VERSION_PATTERN = re.compile(r"tag: (\d+\.\d+\.\d+)")
PULL_REQUEST_INDICATOR = "Merge pull request #"

COMMIT_CODES_TO_HEADINGS_MAPPING = {
    "FEA": "### New features",
    "ENH": "### Enhancements",
    "FIX": "### Fixes",
    "OPS": "### Operations",
    "DEP": "### Dependencies",
    "REF": "### Refactoring",
    "TST": "### Testing",
    "MRG": "### Other",
    "REV": "### Reversions",
    "CHO": "### Chores",
    "WIP": "### Other",
    "DOC": "### Other",
    "STY": "### Other",
}

AUTO_GENERATION_START_INDICATOR = "<!--- START AUTOGENERATED NOTES --->"
AUTO_GENERATION_END_INDICATOR = "<!--- END AUTOGENERATED NOTES --->"
SKIP_INDICATOR = "<!--- SKIP AUTOGENERATED NOTES --->"


class ReleaseNoteCompiler:
    """A release/pull request notes compiler. The notes are pulled together from Conventional Commit messages, stopping
    at the specified stop point. The stop point can either be the last merged pull request in the branch or the last
    semantically-versioned release tagged in the branch. If previous notes are provided, only the text between the
    comment lines `<!--- START AUTOGENERATED NOTES --->` and `<!--- END AUTOGENERATED NOTES --->` will be replaced -
    anything outside of this will appear in the new release notes.

    :param str stop_point: the point in the git history up to which commit messages should be used - should be either "LAST_RELEASE" or "LAST_PULL_REQUEST"
    :param str|None pull_request_url: GitHub API URL for the pull request - this can be accessed in a GitHub workflow as ${{ github.event.pull_request.url }}
    :param str|None api_token: GitHub API token - this can be accessed in a GitHub workflow as ${{ secrets.GITHUB_TOKEN }}
    :param str header: the header to put above the autogenerated release notes, including any markdown styling (defaults to "## Contents")
    :param str list_item_symbol: the markdown symbol to use for listing the commit messages in the release notes (defaults to a ticked checkbox but could be a bullet point or number)
    :param dict|None commit_codes_to_headings_mapping: mapping of commit codes to the header they should be put under, including markdown styling (e.g. "### Fixes")
    :return None:
    """

    def __init__(
        self,
        stop_point,
        pull_request_url=None,
        api_token=None,
        header="## Contents",
        list_item_symbol="- [x] ",
        commit_codes_to_headings_mapping=None,
    ):
        if stop_point.upper() not in {LAST_RELEASE, LAST_PULL_REQUEST}:
            raise ValueError(
                f"`stop_point` must be one of {LAST_RELEASE, LAST_PULL_REQUEST!r}; received {stop_point!r}."
            )

        self.stop_point = stop_point.upper()

        if pull_request_url:
            self.previous_notes = self._get_current_pull_request_description(pull_request_url, api_token)
        else:
            self.previous_notes = None

        self.header = header
        self.list_item_symbol = list_item_symbol
        self.commit_codes_to_headings_mapping = commit_codes_to_headings_mapping or COMMIT_CODES_TO_HEADINGS_MAPPING

    def compile_release_notes(self):
        """Compile the commit messages since the given stop point into a new set of release notes, sorting them into
        headed sections according to their commit codes via the commit-codes-to-headings mapping. If the previous set
        of release notes have been provided then:

        * If the skip indicator is present, the previous notes are returned as they are
        * Otherwise if the autogeneration indicators are present, the previous notes are left unchanged apart from
          between these indicators, where the new autogenerated release notes overwrite whatever was between them before
        * If the autogeneration indicators are not present, the new autogenerated release notes are added after the
          previous notes

        :return str:
        """
        if self.previous_notes and SKIP_INDICATOR in self.previous_notes:
            return self.previous_notes

        git_log = self._get_git_log()
        parsed_commits, unparsed_commits = self._parse_commit_messages(git_log)
        categorised_commit_messages = self._categorise_commit_messages(parsed_commits, unparsed_commits)
        autogenerated_release_notes = self._build_release_notes(categorised_commit_messages)

        if not self.previous_notes:
            return autogenerated_release_notes

        previous_notes_before_generated_section = self.previous_notes.split(AUTO_GENERATION_START_INDICATOR)
        previous_notes_after_generated_section = "".join(previous_notes_before_generated_section[1:]).split(
            AUTO_GENERATION_END_INDICATOR
        )

        return "\n".join(
            (
                previous_notes_before_generated_section[0].strip("\n"),
                autogenerated_release_notes,
                previous_notes_after_generated_section[-1].strip("\n"),
            )
        ).strip('"\n')

    def _get_current_pull_request_description(self, pull_request_url, api_token):
        """Get the current pull request description (body) from the GitHub API.

        :param str pull_request_url: the GitHub API URL for the pull request
        :param str|None api_token: GitHub API token
        :return str:
        """
        if api_token is None:
            headers = {}
        else:
            headers = {"Authorization": f"token {api_token}"}

        return requests.get(pull_request_url, headers=headers).json()["body"]

    def _get_git_log(self):
        """Get the one-line decorated git log formatted with "|" separating the message and decoration.

        :return str:
        """
        return subprocess.run(["git", "log", "--pretty=format:%s|%d"], capture_output=True).stdout.strip().decode()

    def _parse_commit_messages(self, formatted_oneline_git_log):
        """Parse commit messages from the git log (formatted using `--pretty=format:%s|%d`) until the stop point is
        reached. The parsed commit messages are returned separately to any that fail to parse.

        :param str formatted_oneline_git_log:
        :return list(tuple), list(str):
        """
        parsed_commits = []
        unparsed_commits = []

        for commit in formatted_oneline_git_log.splitlines():
            # The pipe symbol "|" is used to delimit the commit header from its decoration.
            split_commit = commit.split("|")

            if len(split_commit) == 2:
                message, decoration = split_commit

                if self._is_stop_point(message, decoration):
                    break

                # A colon separating the commit code from the commit header is required - keep commit messages that
                # don't conform to this but put them into an unparsed category.
                if ":" not in message:
                    unparsed_commits.append(message.strip())
                    continue

                # Allow commit headers with extra colons.
                code, *message = message.split(":")
                message = ":".join(message)

                parsed_commits.append((code.strip(), message.strip(), decoration.strip()))

        return parsed_commits, unparsed_commits

    def _is_stop_point(self, message, decoration):
        """Check if this commit header is the stop point for collecting commits for the release notes.

        :param str message:
        :param str decoration:
        :return bool:
        """
        if self.stop_point == LAST_RELEASE:
            if "tag" in decoration:
                return bool(SEMANTIC_VERSION_PATTERN.search(decoration))

        if self.stop_point == LAST_PULL_REQUEST:
            return PULL_REQUEST_INDICATOR in message

    def _categorise_commit_messages(self, parsed_commits, unparsed_commits):
        """Categorise the commit messages into headed sections. Unparsed commits are put under an "uncategorised"
        header.

        :param iter(tuple)) parsed_commits:
        :param iter(str) unparsed_commits:
        :return dict:
        """
        release_notes = {heading: [] for heading in self.commit_codes_to_headings_mapping.values()}

        for code, message, _ in parsed_commits:
            try:
                release_notes[self.commit_codes_to_headings_mapping[code]].append(message)
            except KeyError:
                release_notes["### Other"].append(message)

        release_notes["### Uncategorised!"] = unparsed_commits
        return release_notes

    def _build_release_notes(self, categorised_commit_messages):
        """Build the the categorised commit messages into a single multi-line string ready to be used as formatted
        release notes.

        :param dict categorised_commit_messages:
        :return str:
        """
        release_notes_for_printing = f"{AUTO_GENERATION_START_INDICATOR}\n{self.header}\n\n"

        for heading, notes in categorised_commit_messages.items():

            if len(notes) == 0:
                continue

            note_lines = "\n".join(self.list_item_symbol + note for note in notes)
            release_notes_for_printing += f"{heading}\n{note_lines}\n\n"

        release_notes_for_printing += AUTO_GENERATION_END_INDICATOR
        return release_notes_for_printing


def main():
    release_notes = ReleaseNoteCompiler(*sys.argv[1:]).compile_release_notes()
    print(release_notes)


if __name__ == "__main__":
    main()
