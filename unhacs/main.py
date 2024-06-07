import json
import shutil
import tempfile
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests

from unhacs.packages import DEFAULT_PACKAGE_FILE
from unhacs.packages import Package
from unhacs.packages import read_packages
from unhacs.packages import write_packages

DEFAULT_HASS_CONFIG_PATH = Path(".")


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


def create_parser():
    parser = ArgumentParser()
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=DEFAULT_HASS_CONFIG_PATH,
        help="The path to the Home Assistant configuration directory.",
    )
    parser.add_argument(
        "--package-file",
        "-p",
        type=Path,
        default=DEFAULT_PACKAGE_FILE,
        help="The path to the package file.",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--verbose", "-v", action="store_true")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("url", type=str, help="The URL of the package.")
    add_parser.add_argument(
        "name", type=str, nargs="?", help="The name of the package."
    )
    add_parser.add_argument(
        "--version", "-v", type=str, help="The version of the package."
    )
    add_parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="Update the package if it already exists.",
    )

    remove_parser = subparsers.add_parser("remove")
    remove_parser.add_argument("packages", nargs="*")

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("packages", nargs="*")

    return parser


class Unhacs:
    def add_package(
        self,
        package_url: str,
        package_name: str | None = None,
        version: str | None = None,
        update: bool = False,
    ):
        # Parse the package URL to get the owner and repo name
        parts = package_url.split("/")
        owner = parts[-2]
        repo = parts[-1]

        # Fetch the releases from the GitHub API
        response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases")
        response.raise_for_status()
        releases = response.json()

        # If a version is provided, check if it exists in the releases
        if version:
            for release in releases:
                if release["tag_name"] == version:
                    break
            else:
                raise ValueError(f"Version {version} does not exist for this package")
        else:
            # If no version is provided, use the latest release
            version = releases[0]["tag_name"]

        if not version:
            raise ValueError("No releases found for this package")

        package = Package(name=package_name or repo, url=package_url, version=version)
        packages = read_packages()

        # Raise an error if the package is already in the list
        if package in packages:
            if update:
                # Remove old version of the package
                packages = [p for p in packages if p.url != package_url]
            else:
                raise ValueError("Package already exists in the list")

        packages.append(package)
        write_packages(packages)

        self.download_package(package)

    def download_package(self, package: Package, replace: bool = True):
        # Parse the package URL to get the owner and repo name
        parts = package.url.split("/")
        owner = parts[-2]
        repo = parts[-1]

        # Fetch the releases from the GitHub API
        response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases")
        response.raise_for_status()
        releases = response.json()

        # Find the release with the specified version
        for release in releases:
            if release["tag_name"] == package.version:
                break
        else:
            raise ValueError(f"Version {package.version} not found for this package")

        # Download the release zip with the specified name
        response = requests.get(release["zipball_url"])
        response.raise_for_status()

        release_zip = ZipFile(BytesIO(response.content))

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(release_zip, tmpdir)

            for file in tmpdir.glob("*"):
                print(file)
            hacs = json.loads((tmpdir / "hacs.json").read_text())
            print(hacs)

            for custom_component in tmpdir.glob("custom_components/*"):
                dest = (
                    DEFAULT_HASS_CONFIG_PATH
                    / "custom_components"
                    / custom_component.name
                )
                if replace:
                    shutil.rmtree(dest, ignore_errors=True)

                shutil.move(custom_component, dest)

    def update_packages(self, package_names: list[str]):
        if not package_names:
            package_urls = [p.url for p in read_packages()]
        else:
            package_urls = [p.url for p in read_packages() if p.name in package_names]

        for package in package_urls:
            print("Updating", package)
            self.add_package(package, update=True)

    def list_packages(self, verbose: bool = False):
        for package in read_packages():
            print(package.verbose_str() if verbose else str(package))


def main():
    # If the sub command is add package, it should pass the parsed arguments to the add_package function and return
    parser = create_parser()
    args = parser.parse_args()

    unhacs = Unhacs()

    if args.subcommand == "add":
        unhacs.add_package(args.url, args.name, args.version, args.update)
    elif args.subcommand == "list":
        unhacs.list_packages(args.verbose)
    elif args.subcommand == "remove":
        print("Not implemented")
    elif args.subcommand == "update":
        unhacs.update_packages(args.packages)
    else:
        print("Not implemented")


if __name__ == "__main__":
    main()
