import shutil
from enum import StrEnum
from enum import auto
from pathlib import Path
from typing import Any
from typing import cast

import requests
import yaml

from unhacs.git import get_repo_tags


class PackageType(StrEnum):
    INTEGRATION = auto()
    PLUGIN = auto()
    FORK = auto()
    THEME = auto()


class Package:
    git_tags = False
    package_type: PackageType

    other_fields: list[str] = []

    def __init__(
        self,
        url: str,
        version: str | None = None,
        ignored_versions: set[str] | None = None,
    ):
        self.url = url
        self.ignored_versions = ignored_versions or set()

        parts = self.url.split("/")
        self.owner = parts[-2]
        self.name = parts[-1]

        self.path: Path | None = None

        if not version:
            self.version = self.fetch_version_release()
        else:
            self.version = version

    def __str__(self):
        return f"{self.package_type}: {self.name} {self.version}"

    def __eq__(self, other):
        return all(
            (
                self.same(other),
                self.version == other.version,
            )
        )

    def same(self, other):
        fields = list(["url"] + self.other_fields)

        return all((getattr(self, field) == getattr(other, field) for field in fields))

    def __hash__(self):
        fields = list(["url"] + self.other_fields)

        return hash(tuple(getattr(self, field) for field in fields))

    def verbose_str(self):
        return f"{str(self)} ({self.url})"

    @classmethod
    def from_yaml(cls, data: dict | Path | str) -> "Package":
        if isinstance(data, Path):
            with data.open() as f:
                data = yaml.safe_load(f)
        elif isinstance(data, str):
            data = yaml.safe_load(data)

        data = cast(dict, data)

        if (package_type := data.pop("package_type")) != cls.package_type:
            raise ValueError(
                f"Invalid package_type ({package_type}) for this class {cls.package_type}"
            )

        return cls(data.pop("url"), **data)

    def to_yaml(self, dest: Path | None = None) -> dict:
        data: dict[str, Any] = {
            "url": self.url,
            "version": self.version,
            "package_type": str(self.package_type),
        }

        if self.ignored_versions:
            data["ignored_versions"] = self.ignored_versions

        for field in self.other_fields:
            if hasattr(self, field):
                data[field] = getattr(self, field)

        if dest:
            with dest.open("w") as f:
                yaml.dump(self.to_yaml(), f)

        return data

    def add_ignored_version(self, version: str):
        self.ignored_versions.add(version)

    def _fetch_version_release_releases(self, version: str | None = None) -> str:
        # Fetch the releases from the GitHub API
        response = requests.get(
            f"https://api.github.com/repos/{self.owner}/{self.name}/releases"
        )
        response.raise_for_status()
        releases = response.json()

        if not releases:
            raise ValueError(f"No releases found for package {self.name}")

        # Default to latest
        desired_release = releases[0]

        # If a version is provided, check if it exists in the releases
        if version:
            for release in releases:
                if release["tag_name"] == version:
                    desired_release = release
                    break
            else:
                raise ValueError(f"Version {version} does not exist for this package")

        return cast(str, desired_release["tag_name"])

    def _fetch_version_release_git(self, version: str | None = None) -> str:
        tags = get_repo_tags(self.url)
        if not tags:
            raise ValueError(f"No tags found for package {self.name}")
        if version and version not in tags:
            raise ValueError(f"Version {version} does not exist for this package")

        tags = [tag for tag in tags if tag not in self.ignored_versions]
        if not version:
            version = tags[-1]

        return version

    def fetch_version_release(self, version: str | None = None) -> str:
        if self.git_tags:
            return self._fetch_version_release_git(version)
        else:
            return self._fetch_version_release_releases(version)

    def _fetch_versions(self) -> list[str]:
        return get_repo_tags(self.url)

    def get_hacs_json(self, version: str | None = None) -> dict:
        """Fetches the hacs.json file for the package."""
        version = version or self.version
        response = requests.get(
            f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{version}/hacs.json"
        )

        if response.status_code == 404:
            return {}

        response.raise_for_status()
        return response.json()

    def install(self, hass_config_path: Path):
        raise NotImplementedError()

    @property
    def unhacs_path(self) -> Path | None:
        if self.path is None:
            return None

        return self.path / "unhacs.yaml"

    def uninstall(self, hass_config_path: Path) -> bool:
        """Uninstalls the package if it is installed, returning True if it was uninstalled."""
        if not self.path:
            if installed_package := self.installed_package(hass_config_path):
                installed_package.uninstall(hass_config_path)
                return True

            return False

        if self.path.is_dir():
            shutil.rmtree(self.path)
        else:
            self.path.unlink()
            if self.unhacs_path and self.unhacs_path.exists():
                self.unhacs_path.unlink()

        return True

    @classmethod
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        raise NotImplementedError()

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list["Package"]:
        raise NotImplementedError()

    def installed_package(self, hass_config_path: Path) -> "Package|None":
        """Returns the installed package if it exists, otherwise None."""
        for package in self.find_installed(hass_config_path):
            if self.same(package):
                return package

        return None

    def is_update(self, hass_config_path: Path) -> bool:
        """Returns True if the package is not installed or the installed version is different from the latest."""
        installed_package = self.installed_package(hass_config_path)
        return installed_package is None or installed_package.version != self.version

    def get_latest(self) -> "Package":
        """Returns a new Package representing the latest version of this package."""
        package = self.to_yaml()
        package.pop("version")
        package.pop("package_type")
        return self.__class__(package.pop("url"), **package)
