import json
import shutil
import tempfile
from collections.abc import Generator
from collections.abc import Iterable
from enum import StrEnum
from enum import auto
from io import BytesIO
from pathlib import Path
from typing import Any
from typing import cast
from zipfile import ZipFile

import requests
import yaml

from unhacs.git import get_branch_zip
from unhacs.git import get_latest_sha
from unhacs.git import get_repo_tags
from unhacs.git import get_tag_zip

DEFAULT_HASS_CONFIG_PATH: Path = Path(".")
DEFAULT_PACKAGE_FILE = Path("unhacs.yaml")


def extract_zip(zip_file: ZipFile, dest_dir: Path):
    for info in zip_file.infolist():
        if info.is_dir():
            continue
        file = Path(info.filename)
        # Strip top directory from path
        file = Path(*file.parts[1:])
        path = dest_dir / file
        path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(info) as source, open(path, "wb") as dest:
            dest.write(source.read())


class PackageType(StrEnum):
    INTEGRATION = auto()
    PLUGIN = auto()
    FORK = auto()


class Package:
    git_tags = False

    def __init__(
        self,
        url: str,
        version: str | None = None,
        package_type: PackageType = PackageType.INTEGRATION,
        ignored_versions: set[str] | None = None,
        branch_name: str | None = None,
        fork_component: str | None = None,
    ):
        if package_type == PackageType.FORK and not fork_component:
            raise ValueError(f"Fork with no component specified {url}@{branch_name}")

        self.url = url
        self.package_type = package_type
        self.fork_component = fork_component
        self.ignored_versions = ignored_versions or set()
        self.branch_name = branch_name

        parts = self.url.split("/")
        self.owner = parts[-2]
        self.name = parts[-1]

        self.path: Path | None = None

        if not version:
            self.version = self.fetch_version_release()
        else:
            self.version = version

    def __str__(self):
        name = self.name
        if self.fork_component:
            name = f"{self.fork_component} ({name})"
        version = self.version
        if self.branch_name:
            version = f"{version} ({self.branch_name})"
        return f"{self.package_type}: {name} {version}"

    def __eq__(self, other):
        return all(
            (
                self.same(other),
                self.fork_component == other.fork_component,
            )
        )

    def same(self, other):
        return all(
            (
                self.url == other.url,
                self.branch_name == other.branch_name,
                self.fork_component == other.fork_component,
            )
        )

    def __hash__(self):
        return hash((self.url, self.branch_name, self.fork_component))

    def verbose_str(self):
        return f"{str(self)} ({self.url})"

    @staticmethod
    def from_yaml(yml: dict) -> "Package":
        # Convert package_type to enum
        package_type = yml.pop("package_type", None)
        if package_type and isinstance(package_type, str):
            package_type = PackageType(package_type)
            yml["package_type"] = package_type

        return Package(**yml)

    def to_yaml(self: "Package") -> dict:
        data: dict[str, Any] = {
            "url": self.url,
            "version": self.version,
            "package_type": str(self.package_type),
        }

        if self.branch_name:
            data["branch_name"] = self.branch_name
        if self.fork_component:
            data["fork_component"] = self.fork_component
        if self.ignored_versions:
            data["ignored_versions"] = self.ignored_versions

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

    def _fetch_latest_sha(self, branch_name: str) -> str:
        return get_latest_sha(self.url, branch_name)

    def fetch_version_release(self, version: str | None = None) -> str:
        if self.branch_name:
            return self._fetch_latest_sha(self.branch_name)
        elif self.git_tags:
            return self._fetch_version_release_git(version)
        else:
            return self._fetch_version_release_releases(version)

    def fetch_versions(self) -> list[str]:
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

    def install_plugin(self, hass_config_path: Path):
        """Installs the plugin package."""

        valid_filenames: Iterable[str]
        if filename := self.get_hacs_json().get("filename"):
            valid_filenames = (cast(str, filename),)
        else:
            valid_filenames = (
                f"{self.name.removeprefix('lovelace-')}.js",
                f"{self.name}.js",
                f"{self.name}-umd.js",
                f"{self.name}-bundle.js",
            )

        def real_get(filename) -> requests.Response | None:
            urls = [
                f"https://raw.githubusercontent.com/{self.owner}/{self.version}/dist/{filename}",
                f"https://github.com/{self.owner}/{self.name}/releases/download/{self.version}/{filename}",
                f"https://raw.githubusercontent.com/{self.owner}/{self.version}/{filename}",
            ]

            for url in urls:
                plugin = requests.get(url)

                if int(plugin.status_code / 100) == 4:
                    continue

                plugin.raise_for_status()

                return plugin

            return None

        for filename in valid_filenames:
            plugin = real_get(filename)
            if plugin:
                break
        else:
            raise ValueError(f"No valid filename found for package {self.name}")

        js_path = hass_config_path / "www" / "js"
        js_path.mkdir(parents=True, exist_ok=True)
        js_path.joinpath(filename).write_text(plugin.text)

        yaml.dump(self.to_yaml(), js_path.joinpath(f"{filename}-unhacs.yaml").open("w"))

        # Write to resources
        resources: list[dict] = []
        resources_file = hass_config_path / "resources.yaml"
        if resources_file.exists():
            resources = yaml.safe_load(resources_file.open()) or []

        if not any(r["url"] == f"/local/js/{filename}" for r in resources):
            resources.append(
                {
                    "url": f"/local/js/{filename}",
                    "type": "module",
                }
            )

        yaml.dump(resources, resources_file.open("w"))

    def install_integration(self, hass_config_path: Path):
        """Installs the integration package."""
        zipball_url = get_tag_zip(self.url, self.version)
        response = requests.get(zipball_url)
        response.raise_for_status()

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            source, dest = None, None
            for custom_component in tmpdir.glob("custom_components/*"):
                source = custom_component
                dest = hass_config_path / "custom_components" / custom_component.name
                break
            else:
                hacs_json = json.loads((tmpdir / "hacs.json").read_text())
                if hacs_json.get("content_in_root"):
                    source = tmpdir
                    dest = hass_config_path / "custom_components" / self.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(source, dest)

            yaml.dump(self.to_yaml(), dest.joinpath("unhacs.yaml").open("w"))

    def install_fork_component(self, hass_config_path: Path):
        """Installs the integration from hass fork."""
        if not self.fork_component:
            raise ValueError(f"No fork component specified for {self.verbose_str()}")
        if not self.branch_name:
            raise ValueError(f"No branch name specified for {self.verbose_str()}")

        zipball_url = get_branch_zip(self.url, self.branch_name)
        response = requests.get(zipball_url)
        response.raise_for_status()

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            source, dest = None, None
            source = tmpdir / "homeassistant" / "components" / self.fork_component
            if not source.exists() or not source.is_dir():
                raise ValueError(
                    f"Could not find {self.fork_component} in {self.url}@{self.version}"
                )

            # Add version to manifest
            manifest_file = source / "manifest.json"
            manifest = json.load(manifest_file.open())
            manifest["version"] = "0.0.0"
            json.dump(manifest, manifest_file.open("w"))

            dest = hass_config_path / "custom_components" / source.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(source, dest)

            yaml.dump(self.to_yaml(), dest.joinpath("unhacs.yaml").open("w"))

    def install(self, hass_config_path: Path):
        """Installs the package."""
        if self.package_type == PackageType.PLUGIN:
            self.install_plugin(hass_config_path)
        elif self.package_type == PackageType.INTEGRATION:
            self.install_integration(hass_config_path)
        elif self.package_type == PackageType.FORK:
            self.install_fork_component(hass_config_path)
        else:
            raise NotImplementedError(f"Unknown package type {self.package_type}")

    def uninstall(self, hass_config_path: Path) -> bool:
        """Uninstalls the package if it is installed, returning True if it was uninstalled."""
        if not self.path:
            print("No path found for package, searching...")
            if installed_package := self.installed_package(hass_config_path):
                installed_package.uninstall(hass_config_path)
                return True

            return False

        print("Removing", self.path)

        if self.path.is_dir():
            shutil.rmtree(self.path)
        else:
            self.path.unlink()
            self.path.with_name(f"{self.path.name}-unhacs.yaml").unlink()

            # Remove from resources
            resources_file = hass_config_path / "resources.yaml"
            if resources_file.exists():
                with resources_file.open("r") as f:
                    resources = yaml.safe_load(f) or []
                new_resources = [
                    r for r in resources if r["url"] != f"/local/js/{self.path.name}"
                ]
                if len(new_resources) != len(resources):

                    with resources_file.open("w") as f:
                        yaml.dump(new_resources, f)

        return True

    def installed_package(self, hass_config_path: Path) -> "Package|None":
        """Returns the installed package if it exists, otherwise None."""
        for package in get_installed_packages(hass_config_path, [self.package_type]):
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
        return Package(**package)


def get_installed_packages(
    hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH,
    package_types: Iterable[PackageType] = (
        PackageType.INTEGRATION,
        PackageType.PLUGIN,
    ),
) -> Generator[Package, None, None]:
    # Integration packages
    if PackageType.INTEGRATION in package_types:
        for custom_component in (hass_config_path / "custom_components").glob("*"):
            unhacs = custom_component / "unhacs.yaml"
            if unhacs.exists():
                package = Package.from_yaml(yaml.safe_load(unhacs.open()))
                package.path = custom_component
                yield package

    # Plugin packages
    if PackageType.PLUGIN in package_types:
        for js_unhacs in (hass_config_path / "www" / "js").glob("*-unhacs.yaml"):
            package = Package.from_yaml(yaml.safe_load(js_unhacs.open()))
            package.path = js_unhacs.with_name(
                js_unhacs.name.removesuffix("-unhacs.yaml")
            )
            yield package


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_lock_packages(package_file: Path = DEFAULT_PACKAGE_FILE) -> list[Package]:
    if package_file.exists():
        return [
            Package.from_yaml(p)
            for p in yaml.safe_load(package_file.open())["packages"]
        ]
    return []


# Write a list of Packages to a text file in the format URL version name
def write_lock_packages(
    packages: Iterable[Package], package_file: Path = DEFAULT_PACKAGE_FILE
):
    yaml.dump({"packages": [p.to_yaml() for p in packages]}, package_file.open("w"))
