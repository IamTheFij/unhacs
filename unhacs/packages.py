import json
import shutil
import tempfile
from collections.abc import Iterable
from enum import StrEnum
from enum import auto
from io import BytesIO
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import requests
import yaml

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


class Package:
    url: str
    owner: str
    name: str
    version: str
    download_url: str
    path: Path | None = None
    package_type: PackageType = PackageType.INTEGRATION

    def __init__(
        self,
        url: str,
        version: str | None = None,
        package_type: PackageType = PackageType.INTEGRATION,
    ):
        self.url = url
        self.package_type = package_type

        parts = self.url.split("/")
        self.owner = parts[-2]
        self.name = parts[-1]

        if not version:
            self.version, self.download_url = self.fetch_version_release(version)
        else:
            self.version = version

    def __str__(self):
        return f"{self.name} {self.version}"

    def __eq__(self, other):
        return self.url == other.url and self.version == other.version

    def verbose_str(self):
        return f"{self.name} {self.version} ({self.url})"

    @staticmethod
    def from_yaml(yaml: dict) -> "Package":
        # Convert package_type to enum
        package_type = yaml.pop("package_type")
        if package_type and isinstance(package_type, str):
            package_type = PackageType(package_type)
            yaml["package_type"] = package_type

        return Package(**yaml)

    def to_yaml(self: "Package") -> dict:
        return {
            "url": self.url,
            "version": self.version,
            "package_type": str(self.package_type),
        }

    def fetch_version_release(self, version: str | None = None) -> tuple[str, str]:
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

        version = cast(str, desired_release["tag_name"])
        hacs_json = self.get_hacs_json(version)

        # Based on type, if we have no hacs json, we can provide some possible paths for the download but won't know
        # If a plugin:
        # First, check in root/dist/ for a js file named the same as the repo or with "lovelace-" prefix removed
        # Second will be looking for a realeases for a js file named the same name as the repo or with loveace- prefix removed
        # Third will be looking in the root dir for a js file named the same as the repo or with loveace- prefix removed
        # If an integration:
        # We always use the zipball_url

        download_url = None
        if filename := hacs_json.get("filename"):
            for asset in desired_release["assets"]:
                if asset["name"] == filename:
                    download_url = cast(str, asset["browser_download_url"])
                    break
        else:
            download_url = cast(str, desired_release["zipball_url"])

        if not download_url:
            raise ValueError("No filename found in hacs.json")

        return version, download_url

    def get_hacs_json(self, version: str | None = None) -> dict:
        version = version or self.version
        response = requests.get(
            f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{version}/hacs.json"
        )

        if response.status_code == 404:
            return {}

        response.raise_for_status()
        return response.json()

    def install_plugin(self, hass_config_path: Path):
        # First, check in root/dist/ for a js file named the same as the repo or with "lovelace-" prefix removed
        # Second will be looking for a realeases for a js file named the same name as the repo or with loveace- prefix removed
        # Third will be looking in the root dir for a js file named the same as the repo or with loveace- prefix removed
        # If none of these are found, raise an error
        # If a file is found, write it to www/js/<filename>.js and write a file www/js/<filename>-unhacs.txt with the
        # serialized package

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

        def real_get(filename) -> requests.Response:
            plugin = requests.get(
                f"https://raw.githubusercontent.com/{self.owner}/{self.version}/dist/{filename}"
            )
            if plugin.status_code == 404:
                plugin = requests.get(
                    f"https://github.com/{self.owner}/{self.name}/releases/download/{self.version}/{filename}"
                )
            if plugin.status_code == 404:
                plugin = requests.get(
                    f"https://raw.githubusercontent.com/{self.owner}/{self.version}/{filename}"
                )

            plugin.raise_for_status()
            return plugin

        for filename in valid_filenames:
            try:
                plugin = real_get(filename)
                break
            except requests.HTTPError:
                pass
        else:
            raise ValueError(f"No valid filename found for package {self.name}")

        js_path = hass_config_path / "www" / "js"
        js_path.mkdir(parents=True, exist_ok=True)
        js_path.joinpath(filename).write_text(plugin.text)

        yaml.dump(self.to_yaml(), js_path.joinpath(f"{filename}-unhacs.yaml").open("w"))

    def install_integration(self, hass_config_path: Path):
        zipball_url = f"https://codeload.github.com/{self.owner}/{self.name}/zip/refs/tags/{self.version}"
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

    def install(self, hass_config_path: Path):
        if self.package_type == PackageType.PLUGIN:
            self.install_plugin(hass_config_path)
        elif self.package_type == PackageType.INTEGRATION:
            self.install_integration(hass_config_path)
        else:
            raise NotImplementedError(f"Unknown package type {self.package_type}")

    def uninstall(self, hass_config_path: Path) -> bool:
        if self.path:
            if self.path.is_dir():
                shutil.rmtree(self.path)
            else:
                self.path.unlink()
                self.path.with_name(f"{self.path.name}-unhacs.yaml").unlink()
            return True

        installed_package = self.installed_package(hass_config_path)
        if installed_package:
            installed_package.uninstall(hass_config_path)
            return True

        return False

    def installed_package(self, hass_config_path: Path) -> "Package|None":
        for custom_component in (hass_config_path / "custom_components").glob("*"):
            unhacs = custom_component / "unhacs.yaml"
            if unhacs.exists():
                installed_package = Package.from_yaml(yaml.safe_load(unhacs.open()))
                installed_package.path = custom_component
                if (
                    installed_package.name == self.name
                    and installed_package.url == self.url
                ):
                    return installed_package

        for js_unhacs in (hass_config_path / "www" / "js").glob("*-unhacs.yaml"):
            installed_package = Package.from_yaml(yaml.safe_load(js_unhacs.open()))
            installed_package.path = js_unhacs.with_name(
                js_unhacs.name.removesuffix("-unhacs.yaml")
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

    # Integration packages
    for custom_component in (hass_config_path / "custom_components").glob("*"):
        unhacs = custom_component / "unhacs.yaml"
        if unhacs.exists():
            package = Package.from_yaml(yaml.safe_load(unhacs.open()))
            package.path = custom_component
            packages.append(package)

    # Plugin packages
    for js_unhacs in (hass_config_path / "www" / "js").glob("*-unhacs.yaml"):
        package = Package.from_yaml(yaml.safe_load(js_unhacs.open()))
        package.path = js_unhacs.with_name(js_unhacs.name.removesuffix("-unhacs.yaml"))
        packages.append(package)

    return packages


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
