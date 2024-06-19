from argparse import ArgumentParser
from pathlib import Path

from unhacs.packages import DEFAULT_HASS_CONFIG_PATH
from unhacs.packages import DEFAULT_PACKAGE_FILE
from unhacs.packages import Package
from unhacs.packages import get_installed_packages
from unhacs.packages import read_lock_packages
from unhacs.packages import write_lock_packages


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

    remove_parser = subparsers.add_parser("remove")
    remove_parser.add_argument("packages", nargs="+")

    update_parser = subparsers.add_parser("upgrade")
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
        package = Package(name=package_name, url=package_url, version=version)
        packages = read_lock_packages()

        # Raise an error if the package is already in the list
        if package in packages:
            if update:
                # Remove old version of the package
                packages = [p for p in packages if p != package]
            else:
                raise ValueError("Package already exists in the list")

        package.install()

        packages.append(package)
        write_lock_packages(packages)

    def upgrade_packages(self, package_names: list[str]):
        if not package_names:
            packages = read_lock_packages()
        else:
            packages = [p for p in read_lock_packages() if p.name in package_names]

        latest_packages = [Package(name=p.name, url=p.url) for p in packages]
        for package, latest_package in zip(packages, latest_packages):
            if latest_package.outdated():
                print(
                    f"upgrade {package.name} from {package.version} to {latest_package.version}"
                )

        # Prompt the user to press Y to continue and upgrade all packages, otherwise exit
        if input("Upgrade all packages? (y/N) ").lower() != "y":
            return

        for package in latest_packages:
            package.install()

        latest_lookup = {p.url: p for p in latest_packages}
        packages = [latest_lookup.get(p.url, p) for p in read_lock_packages()]

        write_lock_packages(packages)

    def list_packages(self, verbose: bool = False):
        for package in get_installed_packages():
            print(package.verbose_str() if verbose else str(package))

    def remove_packages(self, package_names: list[str]):
        packages_to_remove = [
            package
            for package in get_installed_packages()
            if package.name in package_names
        ]
        remaining_packages = [
            package
            for package in read_lock_packages()
            if package not in packages_to_remove
        ]

        for package in packages_to_remove:
            package.uninstall()

        write_lock_packages(remaining_packages)


def main():
    # If the sub command is add package, it should pass the parsed arguments to the add_package function and return
    parser = create_parser()
    args = parser.parse_args()

    unhacs = Unhacs()

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


if __name__ == "__main__":
    main()
