import json
import shutil
import tempfile
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests

DEFAULT_HASS_CONFIG_PATH: Path = Path(".")
DEFAULT_PACKAGE_FILE = "unhacs.txt"


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


class Package:
    url: str
    version: str
    zip_url: str
    name: str
    path: Path | None = None

    def __init__(self, url: str, version: str | None = None, name: str | None = None):
        self.url = url

        if not version:
            self.version, self.zip_url = self.fetch_version_release(version)
        else:
            self.version = version

        parts = url.split("/")
        repo = parts[-1]
        self.name = name or repo

    def __str__(self):
        return f"{self.name} {self.version}"

    def __eq__(self, other):
        return (
            self.url == other.url
            and self.version == other.version
            and self.name == other.name
        )

    def verbose_str(self):
        return f"{self.name} {self.version} ({self.url})"

    def serialize(self) -> str:
        return f"{self.url} {self.version} {self.name}"

    @staticmethod
    def deserialize(serialized: str) -> "Package":
        url, version, name = serialized.split()
        return Package(url, version, name)

    def fetch_version_release(self, version: str | None = None) -> tuple[str, str]:
        # Fetch the releases from the GitHub API
        parts = self.url.split("/")
        owner = parts[-2]
        repo = parts[-1]

        response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases")
        response.raise_for_status()
        releases = response.json()

        if not releases:
            raise ValueError(f"No releases found for package {self.name}")

        # If a version is provided, check if it exists in the releases
        if version:
            for release in releases:
                if release["tag_name"] == version:
                    return version, release["zipball_url"]
            else:
                raise ValueError(f"Version {version} does not exist for this package")
        # If no version is provided, use the latest release
        return releases[0]["tag_name"], releases[0]["zipball_url"]

    def install(
        self, hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH, replace: bool = True
    ):
        # Fetch the release zip with the specified version
        if not self.zip_url:
            _, self.zip_url = self.fetch_version_release(self.version)

        response = requests.get(self.zip_url)
        response.raise_for_status()

        # Extract the zip to a temporary directory
        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            hacs = json.loads((tmpdir / "hacs.json").read_text())
            print("Hacs?", hacs)

            for custom_component in tmpdir.glob("custom_components/*"):
                dest = hass_config_path / "custom_components" / custom_component.name
                if replace:
                    shutil.rmtree(dest, ignore_errors=True)

                shutil.move(custom_component, dest)
                dest.joinpath("unhacs.txt").write_text(self.serialize())

    def uninstall(self, hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH) -> bool:
        if self.path:
            shutil.rmtree(self.path)
            return True

        installed_package = self.installed_package(hass_config_path)
        if installed_package and installed_package.path:
            shutil.rmtree(installed_package.path)
            return True

        return False

    def installed_package(
        self, hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH
    ) -> "Package|None":
        for custom_component in (hass_config_path / "custom_components").glob("*"):
            unhacs = custom_component / "unhacs.txt"
            if unhacs.exists():
                installed_package = Package.deserialize(unhacs.read_text())
                installed_package.path = custom_component
                if (
                    installed_package.name == self.name
                    and installed_package.url == self.url
                ):
                    return installed_package
        return None

    def outdated(self) -> bool:
        installed_package = self.installed_package()
        return installed_package is None or installed_package.version != self.version


def get_installed_packages(
    hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH,
) -> list[Package]:
    packages = []
    for custom_component in (hass_config_path / "custom_components").glob("*"):
        unhacs = custom_component / "unhacs.txt"
        if unhacs.exists():
            package = Package.deserialize(unhacs.read_text())
            package.path = custom_component
            packages.append(package)

    return packages


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_lock_packages(package_file: str = DEFAULT_PACKAGE_FILE) -> list[Package]:
    path = Path(package_file)
    if path.exists():
        with path.open() as f:
            return [Package.deserialize(line.strip()) for line in f]
    return []


# Write a list of Packages to a text file in the format URL version name
def write_lock_packages(
    packages: Iterable[Package], package_file: str = DEFAULT_PACKAGE_FILE
):
    with open(package_file, "w") as f:
        f.writelines(f"{package.serialize()}\n" for package in packages)
