import json
import shutil
import tempfile
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.parse import urlparse
from zipfile import ZipFile

import requests

DEFAULT_HASS_CONFIG_PATH: Path = Path(".")
DEFAULT_PACKAGE_FILE = Path("unhacs.txt")


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
    owner: str
    repo: str
    version: str
    download_url: str
    name: str
    path: Path | None = None

    def __init__(self, url: str, version: str | None = None, name: str | None = None):
        self.url = url

        parts = self.url.split("/")
        self.owner = parts[-2]
        self.repo = parts[-1]

        if not version:
            self.version, self.download_url = self.fetch_version_release(version)
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
        response = requests.get(
            f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
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

        version = cast(str, desired_release["tag_name"])
        hacs_json = self.get_hacs_json(version)

        download_url = None
        if hacs_json.get("content_in_root", True):
            download_url = cast(str, desired_release["zipball_url"])
        elif filename := hacs_json.get("filename"):
            for asset in desired_release["assets"]:
                if asset["name"] == filename:
                    download_url = cast(str, asset["browser_download_url"])
                    break

        if not download_url:
            raise ValueError("No filename found in hacs.json")

        return version, download_url

    def get_hacs_json(self, version: str | None = None) -> dict:
        version = version or self.version
        response = requests.get(
            f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{version}/hacs.json"
        )
        response.raise_for_status()
        return response.json()

    def install(self, hass_config_path: Path, replace: bool = True):
        # Fetch the download for the specified version
        if not self.download_url:
            _, self.download_url = self.fetch_version_release(self.version)

        response = requests.get(self.download_url)
        response.raise_for_status()

        if "/zipball/" in self.download_url:
            # Extract the zip to a temporary directory
            with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
                tmpdir = Path(tempdir)
                extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

                for custom_component in tmpdir.glob("custom_components/*"):
                    dest = (
                        hass_config_path / "custom_components" / custom_component.name
                    )
                    dest.mkdir(parents=True, exist_ok=True)
                    if replace:
                        shutil.rmtree(dest, ignore_errors=True)

                    shutil.move(custom_component, dest)
                    dest.joinpath("unhacs.txt").write_text(self.serialize())
        elif self.download_url.endswith(".js"):
            basename = urlparse(self.download_url).path.split("/")[-1]
            js_path = hass_config_path / "www" / "js"
            js_path.mkdir(parents=True, exist_ok=True)
            js_path.joinpath(basename).write_text(response.text)
            js_path.joinpath(f"{basename}-unhacs.txt").write_text(self.serialize())
        else:
            raise ValueError(f"Unknown download type: {self.download_url}")

    def uninstall(self, hass_config_path: Path) -> bool:
        if self.path:
            if self.path.is_dir():
                shutil.rmtree(self.path)
            else:
                self.path.unlink()
            return True

        installed_package = self.installed_package(hass_config_path)
        if installed_package:
            installed_package.uninstall(hass_config_path)
            return True

        return False

    def installed_package(self, hass_config_path: Path) -> "Package|None":
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

        for js_unhacs in (hass_config_path / "www" / "js").glob("*-unhacs.txt"):
            installed_package = Package.deserialize(js_unhacs.read_text())
            installed_package.path = js_unhacs.with_name(
                js_unhacs.name.removesuffix("-unhacs.txt")
            )
            if (
                installed_package.name == self.name
                and installed_package.url == self.url
            ):
                return installed_package

        return None

    def is_update(self, hass_config_path: Path) -> bool:
        installed_package = self.installed_package(hass_config_path)
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
    for js_unhacs in (hass_config_path / "www" / "js").glob("*-unhacs.txt"):
        package = Package.deserialize(js_unhacs.read_text())
        package.path = js_unhacs.with_name(js_unhacs.name.removesuffix("-unhacs.txt"))
        packages.append(package)

    return packages


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_lock_packages(package_file: Path = DEFAULT_PACKAGE_FILE) -> list[Package]:
    if package_file.exists():
        with package_file.open() as f:
            return [Package.deserialize(line.strip()) for line in f]
    return []


# Write a list of Packages to a text file in the format URL version name
def write_lock_packages(
    packages: Iterable[Package], package_file: Path = DEFAULT_PACKAGE_FILE
):
    with package_file.open("w") as f:
        f.writelines(sorted(f"{package.serialize()}\n" for package in packages))
