from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path

from unhacs.packages import DEFAULT_HASS_CONFIG_PATH
from unhacs.packages import DEFAULT_PACKAGE_FILE
from unhacs.packages import Package
from unhacs.packages import get_installed_packages
from unhacs.packages import read_lock_packages
from unhacs.packages import write_lock_packages


def create_parser():
    parser = ArgumentParser(
        description="Unhacs - Command line interface for the Home Assistant Community Store"
    )
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

    list_parser = subparsers.add_parser("list", description="List installed packages.")
    list_parser.add_argument("--verbose", "-v", action="store_true")

    add_parser = subparsers.add_parser("add", description="Add or install packages.")
    add_parser.add_argument(
        "--file", "-f", type=Path, help="The path to a package file."
    )
    add_parser.add_argument("url", nargs="?", type=str, help="The URL of the package.")
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

    remove_parser = subparsers.add_parser(
        "remove", description="Remove installed packages."
    )
    remove_parser.add_argument("packages", nargs="+")

    update_parser = subparsers.add_parser(
        "upgrade", description="Upgrade installed packages."
    )
    update_parser.add_argument("packages", nargs="*")

    return parser


class Unhacs:
    def __init__(
        self,
        hass_config: Path = DEFAULT_HASS_CONFIG_PATH,
        package_file: Path = DEFAULT_PACKAGE_FILE,
    ):
        self.hass_config = hass_config
        self.package_file = package_file

    def read_lock_packages(self) -> list[Package]:
        return read_lock_packages(self.package_file)

    def write_lock_packages(self, packages: Iterable[Package]):
        return write_lock_packages(packages, self.package_file)

    def add_package(
        self,
        package_url: str,
        package_name: str | None = None,
        version: str | None = None,
        update: bool = False,
    ):
        """Install and add a package to the lock or install a specific version."""
        package = Package(name=package_name, url=package_url, version=version)
        packages = self.read_lock_packages()

        # Raise an error if the package is already in the list
        if package in packages:
            if update:
                # Remove old version of the package
                packages = [p for p in packages if p != package]
            else:
                raise ValueError("Package already exists in the list")

        package.install(self.hass_config)

        packages.append(package)
        self.write_lock_packages(packages)

    def upgrade_packages(self, package_names: list[str]):
        """Uograde to latest version of packages and update lock."""
        if not package_names:
            installed_packages = get_installed_packages(self.hass_config)
        else:
            installed_packages = [
                p
                for p in get_installed_packages(self.hass_config)
                if p.name in package_names
            ]

        upgrade_packages: list[Package] = []
        latest_packages = [Package(name=p.name, url=p.url) for p in installed_packages]
        for installed_package, latest_package in zip(
            installed_packages, latest_packages
        ):
            if latest_package != installed_package:
                print(
                    f"upgrade {installed_package.name} from {installed_package.version} to {latest_package.version}"
                )
                upgrade_packages.append(latest_package)

        if not upgrade_packages:
            print("Nothing to upgrade")
            return

        if input("Upgrade all packages? (y/N) ").strip().lower() != "y":
            return

        for installed_package in upgrade_packages:
            installed_package.install(self.hass_config)

        # Update lock file to latest now that we know they are uograded
        latest_lookup = {p.url: p for p in latest_packages}
        packages = [latest_lookup.get(p.url, p) for p in self.read_lock_packages()]

        self.write_lock_packages(packages)

    def list_packages(self, verbose: bool = False):
        """List installed packages and their versions."""
        for package in get_installed_packages():
            print(package.verbose_str() if verbose else str(package))

    def remove_packages(self, package_names: list[str]):
        """Remove installed packages and uodate lock."""
        packages_to_remove = [
            package
            for package in get_installed_packages()
            if package.name in package_names
        ]
        remaining_packages = [
            package
            for package in self.read_lock_packages()
            if package not in packages_to_remove
        ]

        for package in packages_to_remove:
            package.uninstall(self.hass_config)

        self.write_lock_packages(remaining_packages)


def main():
    # If the sub command is add package, it should pass the parsed arguments to the add_package function and return
    parser = create_parser()
    args = parser.parse_args()

    unhacs = Unhacs(args.config, args.package_file)

    if args.subcommand == "add":
        # If a file was provided, update all packages based on the lock file
        if args.file:
            packages = read_lock_packages(args.file)
            for package in packages:
                unhacs.add_package(
                    package.url, package.name, package.version, update=True
                )
        elif args.url:
            unhacs.add_package(args.url, args.name, args.version, args.update)
        else:
            raise ValueError("Either a file or a URL must be provided")
    elif args.subcommand == "list":
        unhacs.list_packages(args.verbose)
    elif args.subcommand == "remove":
        unhacs.remove_packages(args.packages)
    elif args.subcommand == "upgrade":
        unhacs.upgrade_packages(args.packages)
    else:
        print(f"Command {args.subcommand} is not implemented")
        exit(1)


if __name__ == "__main__":
    main()
