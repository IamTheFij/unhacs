from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path

from unhacs.git import get_repo_tags
from unhacs.packages import DEFAULT_HASS_CONFIG_PATH
from unhacs.packages import DEFAULT_PACKAGE_FILE
from unhacs.packages import Package
from unhacs.packages import PackageType
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
    parser.add_argument(
        "--use-git",
        "-g",
        action="store_true",
        help="Use git to install packages. This will avoid GitHub API limits.",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    list_parser = subparsers.add_parser("list", description="List installed packages.")
    list_parser.add_argument("--verbose", "-v", action="store_true")

    list_tags_parser = subparsers.add_parser("tags", help="List tags for a package.")
    list_tags_parser.add_argument("url", type=str, help="The URL of the package.")
    list_tags_parser.add_argument(
        "--limit", type=int, default=10, help="The number of tags to display."
    )

    add_parser = subparsers.add_parser("add", description="Add or install packages.")
    add_parser.add_argument(
        "--file", "-f", type=Path, help="The path to a package file."
    )
    add_parser.add_argument(
        "--type",
        "-t",
        type=PackageType,
        help="The type of the package. Defaults to 'integration'.",
    )
    add_parser.add_argument("url", nargs="?", type=str, help="The URL of the package.")
    add_parser.add_argument(
        "--version", "-v", type=str, help="The version of the package."
    )
    add_parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="Update the package if it already exists.",
    )
    add_parser.add_argument(
        "--ignore-versions",
        "-i",
        type=str,
        help="The version of the package to ignore. Multiple can be split by a comma.",
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
        version: str | None = None,
        update: bool = False,
        package_type: PackageType = PackageType.INTEGRATION,
        ignore_versions: set[str] | None = None,
    ):
        """Install and add a package to the lock or install a specific version."""
        package = Package(
            package_url,
            version=version,
            package_type=package_type,
            ignored_versions=ignore_versions,
        )
        packages = self.read_lock_packages()

        # Raise an error if the package is already in the list
        existing_package = next((p for p in packages if p.url == package.url), None)
        if existing_package:
            if update:
                # Remove old version of the package
                packages = [p for p in packages if p.url != package.url]
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

        outdated_packages: list[Package] = []
        latest_packages = [p.get_latest() for p in installed_packages]
        for installed_package, latest_package in zip(
            installed_packages, latest_packages
        ):
            if latest_package != installed_package:
                print(
                    f"upgrade {installed_package.name} from {installed_package.version} to {latest_package.version}"
                )
                outdated_packages.append(latest_package)

        if outdated_packages and input("Upgrade all packages? (y/N) ").lower() != "y":
            return

        for installed_package in outdated_packages:
            installed_package.install(self.hass_config)

        # Update lock file to latest now that we know they are uograded
        latest_lookup = {p.url: p for p in latest_packages}
        packages = [latest_lookup.get(p.url, p) for p in self.read_lock_packages()]

        self.write_lock_packages(packages)

    def list_packages(self, verbose: bool = False):
        """List installed packages and their versions."""
        for package in get_installed_packages():
            print(package.verbose_str() if verbose else str(package))

    def list_tags(self, url: str, limit: int = 10):
        print(f"Tags for {url}:")
        for tag in get_repo_tags(url)[-1 * limit :]:
            print(tag)

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
    Package.use_git = args.use_git

    if args.subcommand == "add":
        # If a file was provided, update all packages based on the lock file
        if args.file:
            packages = read_lock_packages(args.file)
            for package in packages:
                unhacs.add_package(
                    package.url,
                    package.version,
                    update=True,
                    package_type=package.package_type,
                    ignore_versions=package.ignored_versions,
                )
        elif args.url:
            unhacs.add_package(
                args.url,
                version=args.version,
                update=args.update,
                package_type=args.type,
                ignore_versions=(
                    {version for version in args.ignore_versions.split(",")}
                    if args.ignore_versions
                    else None
                ),
            )
        else:
            raise ValueError("Either a file or a URL must be provided")
    elif args.subcommand == "list":
        unhacs.list_packages(args.verbose)
    elif args.subcommand == "tags":
        unhacs.list_tags(args.url, limit=args.limit)
    elif args.subcommand == "remove":
        unhacs.remove_packages(args.packages)
    elif args.subcommand == "upgrade":
        unhacs.upgrade_packages(args.packages)
    else:
        print(f"Command {args.subcommand} is not implemented")
        exit(1)


if __name__ == "__main__":
    main()
