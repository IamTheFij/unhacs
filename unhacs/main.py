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


def parse_args():
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
        "--git-tags",
        "-g",
        action="store_true",
        help="Use git to search for version tags. This will avoid GitHub API limits.",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # List installed packages
    list_parser = subparsers.add_parser("list", description="List installed packages.")
    list_parser.add_argument("--verbose", "-v", action="store_true")

    # List git tags for a given package
    list_tags_parser = subparsers.add_parser("tags", help="List tags for a package.")
    list_tags_parser.add_argument("url", type=str, help="The URL of the package.")
    list_tags_parser.add_argument(
        "--limit", type=int, default=10, help="The number of tags to display."
    )

    # Add packages
    add_parser = subparsers.add_parser("add", description="Add or install packages.")

    package_group = add_parser.add_mutually_exclusive_group(required=True)
    package_group.add_argument(
        "--file", "-f", type=Path, help="The path to a package file."
    )
    package_group.add_argument(
        "url", nargs="?", type=str, help="The URL of the package."
    )

    package_type_group = add_parser.add_mutually_exclusive_group()
    package_type_group.add_argument(
        "--integration",
        action="store_const",
        dest="type",
        const=PackageType.INTEGRATION,
        default=PackageType.INTEGRATION,
        help="The package is an integration.",
    )
    package_type_group.add_argument(
        "--plugin",
        action="store_const",
        dest="type",
        const=PackageType.PLUGIN,
        help="The package is a JavaScript plugin.",
    )
    package_type_group.add_argument(
        "--forked-component",
        type=str,
        dest="component",
        help="Component name from a forked type.",
    )

    add_parser.add_argument(
        "--version", "-v", type=str, help="The version of the package."
    )
    add_parser.add_argument(
        "--branch",
        "-b",
        type=str,
        help="For foked types only, branch that should be used.",
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

    # Remove packages
    remove_parser = subparsers.add_parser(
        "remove", description="Remove installed packages."
    )
    remove_parser.add_argument("packages", nargs="+")

    # Upgrade packages
    update_parser = subparsers.add_parser(
        "upgrade", description="Upgrade installed packages."
    )
    update_parser.add_argument("packages", nargs="*")

    args = parser.parse_args()

    if args.subcommand == "add":
        # Component implies forked package
        if args.component and args.type != PackageType.FORK:
            args.type = PackageType.FORK

        # Branch is only valid for forked packages
        if args.type != PackageType.FORK and args.branch:
            raise ValueError(
                "Branch and component can only be used with forked packages"
            )

    return args


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
        package: Package,
        update: bool = False,
    ):
        """Install and add a package to the lock or install a specific version."""
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
        installed_packages: Iterable[Package]

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
            if (
                package.name in package_names
                or package.url in package_names
                or package.fork_component in package_names
            )
        ]

        if packages_to_remove and input("Remove all packages? (y/N) ").lower() != "y":
            return

        if package_names and not packages_to_remove:
            print("No packages found to remove")
            return

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
    args = parse_args()

    unhacs = Unhacs(args.config, args.package_file)
    Package.git_tags = args.git_tags

    if args.subcommand == "add":
        # If a file was provided, update all packages based on the lock file
        if args.file:
            packages = read_lock_packages(args.file)
            for package in packages:
                unhacs.add_package(
                    package,
                    update=True,
                )
        elif args.url:
            unhacs.add_package(
                Package(
                    args.url,
                    version=args.version,
                    package_type=args.type,
                    ignored_versions=(
                        {version for version in args.ignore_versions.split(",")}
                        if args.ignore_versions
                        else None
                    ),
                    branch_name=args.branch,
                    fork_component=args.component,
                ),
                update=args.update,
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
