import re
import subprocess
from dataclasses import dataclass


@dataclass
class GitTag:
    name: str
    version: tuple[int, int, int]
    suffix: str

    @staticmethod
    def parse(name: str):
        if result := re.match(r"^[v]?([\d.]+)(.*)", name):
            version_str = result.group(1)
            suffix = result.group(2)

            parts = version_str.split(".")
            if len(parts) > 3:
                raise ValueError(f"Invalid version tag: {name}")

            try:
                version = (
                    int(parts[0]),
                    int(parts[1]) if len(parts) > 1 else 0,
                    int(parts[2]) if len(parts) > 2 else 0,
                )
            except ValueError:
                raise ValueError(f"Invalid version tag: {name}")

            return GitTag(name, version, suffix)

    def __str__(self):
        return f"{self.name} {self.version}"

    def __eq__(self, other):
        return self.version == other.version and self.suffix == other.suffix

    def __lt__(self, other):
        return self.version < other.version or (
            self.version == other.version and self.suffix < other.suffix
        )


def get_repo_tags(repository_url: str) -> list[str]:
    # Run the command
    command = f"git -c 'versionsort.suffix=-' ls-remote --tags --sort='v:refname' {repository_url}"
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Check for errors
    if result.returncode != 0:
        raise Exception(f"Error running command: {command}\n{result.stderr.decode()}")

    # Parse the output
    tags: list[GitTag] = []
    for line in result.stdout.decode().split("\n"):
        if line:
            if search_result := re.search(r"refs/tags/(.*)", line):
                tag = search_result.group(1)
                if git_tag := GitTag.parse(tag):
                    tags.append(git_tag)

    tags.sort()

    return [tag.name for tag in tags]


def get_latest_sha(repository_url: str, branch_name: str) -> str:
    command = f"git ls-remote {repository_url} {branch_name}"
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Check for errors
    if result.returncode != 0:
        raise Exception(f"Error running command: {command}\n{result.stderr.decode()}")

    for line in result.stdout.decode().split("\n"):
        if line:
            return line.partition("\t")[0]

    raise ValueError(f"branch name '{branch_name}' not found for {repository_url}")


def get_tag_zip(repository_url: str, tag_name: str) -> str:
    return f"{repository_url}/archive/refs/tags/{tag_name}.zip"


def get_branch_zip(repository_url: str, branch_name: str) -> str:
    return f"{repository_url}/archive/{branch_name}.zip"


def get_sha_zip(repository_url: str, sha: str) -> str:
    return f"{repository_url}/archive/{sha}.zip"
