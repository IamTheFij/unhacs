import shutil
from abc import ABC
from abc import abstractmethod
from collections.abc import Iterable
from enum import StrEnum
from enum import auto
from pathlib import Path
from typing import NotRequired
from typing import TypedDict
from typing import cast
from typing import override

import requests
import yaml

from unhacs.git import get_repo_tags


class IncorrectPackageError(ValueError):
    pass


class PackageType(StrEnum):
    INTEGRATION = auto()
    PLUGIN = auto()
    FORK = auto()
    THEME = auto()


class GithubRelease(TypedDict):
    tag_name: str


class PackageDict(TypedDict):
    url: str
    package_type: str
    version: NotRequired[str]
    ignored_versions: NotRequired[set[str]]


class Package(ABC):
    git_tags: bool = False
    package_type: PackageType
    other_fields: list[str] = []

    def __init__(
        self,
        url: str,
        version: str | None = None,
        ignored_versions: Iterable[str] | None = None,
    ):
        self.url: str = url
        self.ignored_versions: set[str] = (
            set(ignored_versions) if ignored_versions else set()
        )

        parts = self.url.split("/")
        self.owner: str = parts[-2]
        self.name: str = parts[-1]

        self.path: Path | None = None

        self.version: str
        if not version:
            self.version = self.fetch_version_release()
        else:
            self.version = version

    @classmethod
    @abstractmethod
    def path_to_unhacs(cls, path: Path) -> Path:
        """Transforms a Package path to an Unhacs path for the package."""
        ...

    @classmethod
    @abstractmethod
    def unhacs_to_path(cls, path: Path) -> Path:
        """Transforms an Unhacs path for the Package to the package path."""
        ...

    @classmethod
    @abstractmethod
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        """Returns the path relative to the provided config directory this class should install into."""
        ...

    @classmethod
    @abstractmethod
    def unhacs_glob_pattern(cls) -> str:
        """Returns the glob pattern to find this package's unhacs.yaml file."""
        ...

    @abstractmethod
    def install(self, hass_config_path: Path) -> None: ...

    @override
    def __str__(self):
        """String representation of the Package."""
        return f"{self.package_type}: {self.name} {self.version}"

    def verbose_str(self):
        """String representation of package with URL."""
        return f"{str(self)} ({self.url})"

    def _to_hashable(self) -> tuple[str, ...]:
        """Convert Package into a hashable tuple."""
        return (self.url,)

    def same(self, other: "Package") -> bool:
        """Check if two packages are the same, ignoring version."""
        return self._to_hashable() == other._to_hashable()

    @override
    def __eq__(self, other: object) -> bool:
        """Determines if two Packages are identical."""
        if not isinstance(other, Package):
            return False

        return self.same(other) and self.version == other.version

    @override
    def __hash__(self) -> int:
        return hash(self._to_hashable())

    @property
    def unhacs_path(self) -> Path | None:
        """Get the unhacs path from the Package path."""
        if self.path is None:
            return None

        return self.path_to_unhacs(self.path)

    @classmethod
    def _read_yaml(cls, unhacs_path: Path | str) -> PackageDict:
        """Reads from path and validates it matches the class type."""
        if isinstance(unhacs_path, str):
            unhacs_path = Path(unhacs_path)

        with unhacs_path.open() as f:
            data = cast(PackageDict, yaml.safe_load(f))

        if (package_type := data.get("package_type", "unknown")) != cls.package_type:
            raise IncorrectPackageError(
                f"Invalid package_type ({package_type}) for this class {cls.package_type}"
            )

        return data

    @classmethod
    def from_dict(cls, data: PackageDict) -> "Package":
        """Creates a new Package instance from deserialized dict."""
        return cls(
            data["url"],
            version=data.get("version"),
            ignored_versions=data.get("ignored_versions"),
        )

    @classmethod
    def from_yaml(cls, unhacs_path: Path | str) -> "Package":
        """Reads serialized Package from path and creates a new instance."""
        if isinstance(unhacs_path, str):
            unhacs_path = Path(unhacs_path)

        data = cls._read_yaml(unhacs_path)
        new_package = cls.from_dict(data)
        new_package.path = cls.unhacs_to_path(unhacs_path)

        return new_package

    def to_dict(self) -> PackageDict:
        data: PackageDict = {
            "url": self.url,
            "version": self.version,
            "package_type": str(self.package_type),
        }

        if self.ignored_versions:
            data["ignored_versions"] = self.ignored_versions

        return data

    def to_yaml(self, dest: Path | None = None) -> PackageDict:
        """Writes Package to yaml file at path and returns resulting dict."""
        if dest is None:
            dest = self.unhacs_path

        if dest is None:
            raise ValueError("Cannot serialize package without an unhacs path.")

        data = self.to_dict()
        with dest.open("w") as f:
            yaml.dump(data, f)

        return data

    def add_ignored_version(self, version: str):
        self.ignored_versions.add(version)

    def _fetch_version_release_releases(self, version_tag: str | None = None) -> str:
        """Fetch the releases from the GitHub API."""
        url = f"https://api.github.com/repos/{self.owner}/{self.name}/releases/latest"
        if version_tag:
            url = f"https://api.github.com/repos/{self.owner}/{self.name}/releases/tags/{version_tag}"

        response = requests.get(url)
        if response.status_code == 404:
            print(
                f"Release not found for {self.owner}/{self.name}: {version_tag or 'latest'}"
            )
        response.raise_for_status()

        release = cast(GithubRelease, response.json())

        return release["tag_name"]

    def _fetch_version_release_git(self, version: str | None = None) -> str:
        tags = get_repo_tags(self.url)
        if not tags:
            raise ValueError(f"No tags found for package {self.name}")

        if version and version not in tags:
            raise ValueError(f"Version {version} does not exist for this package")

        if not version:
            tags = [tag for tag in tags if tag not in self.ignored_versions]
            version = tags[-1]

        return version

    def fetch_version_release(self, version: str | None = None) -> str:
        if self.git_tags:
            return self._fetch_version_release_git(version)
        else:
            return self._fetch_version_release_releases(version)

    def get_hacs_json(self, version: str | None = None) -> dict[str, str]:
        """Fetches the hacs.json file for the package."""
        version = version or self.version
        response = requests.get(
            f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{version}/hacs.json"
        )

        if response.status_code == 404:
            return {}

        response.raise_for_status()

        return cast(dict[str, str], response.json())

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list["Package"]:
        packages: list[Package] = []

        for unhacs_path in cls.get_install_dir(hass_config_path).glob(
            cls.unhacs_glob_pattern()
        ):
            try:
                package = cls.from_yaml(unhacs_path)
                packages.append(package)
            except IncorrectPackageError:
                # We can skip this error since we're only reading optimistically
                pass

        return packages

    def uninstall(self, hass_config_path: Path) -> bool:
        """Uninstalls the package if it is installed, returning True if it was uninstalled."""
        if not self.path:
            if installed_package := self.installed_package(hass_config_path):
                return installed_package.uninstall(hass_config_path)

            return False

        if self.path.is_dir():
            shutil.rmtree(self.path)
        else:
            self.path.unlink()
            if self.unhacs_path and self.unhacs_path.exists():
                self.unhacs_path.unlink()

        return True

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
        package = self.to_dict()
        del package["version"]
        return self.__class__.from_dict(package)
