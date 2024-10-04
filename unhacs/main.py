import sys
from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path

from unhacs.git import get_repo_tags
from unhacs.packages import Package
from unhacs.packages import get_installed_packages
from unhacs.packages import read_lock_packages
from unhacs.packages import write_lock_packages
from unhacs.packages.fork import Fork
from unhacs.packages.integration import Integration
from unhacs.packages.plugin import Plugin
from unhacs.packages.theme import Theme
from unhacs.utils import DEFAULT_HASS_CONFIG_PATH
from unhacs.utils import DEFAULT_PACKAGE_FILE


class InvalidArgumentsError(ValueError):
    pass


class DuplicatePackageError(ValueError):
    pass


def parse_args(argv: list[str]):
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
    list_parser.add_argument(
        "--freeze",
        "-f",
        action="store_true",
        help="Regenerate unhacs.yaml with installed packages.",
    )

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
        const=Integration,
        default=Integration,
        help="The package is an integration.",
    )
    package_type_group.add_argument(
        "--plugin",
        action="store_const",
        dest="type",
        const=Plugin,
        help="The package is a JavaScript plugin.",
    )
    package_type_group.add_argument(
        "--theme",
        action="store_const",
        dest="type",
        const=Theme,
        help="The package is a theme.",
    )
    package_type_group.add_argument(
        "--fork-component",
        type=str,
        help="Name of component from forked core repo.",
    )
    # Additional arguments for forked packages
    add_parser.add_argument(
        "--fork-branch",
        "-b",
        type=str,
        help="Name of branch of forked core repo. (Only for forked components.)",
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
    remove_parser.add_argument(
        "--yes", "-y", action="store_true", help="Do not prompt for confirmation."
    )
    remove_parser.add_argument("packages", nargs="+")

    # Upgrade packages
    update_parser = subparsers.add_parser(
        "upgrade", description="Upgrade installed packages."
    )
    update_parser.add_argument(
        "--yes", "-y", action="store_true", help="Do not prompt for confirmation."
    )
    update_parser.add_argument("packages", nargs="*")

    args = parser.parse_args(argv)

    if args.subcommand == "add":
        # Component implies forked package
        if args.fork_component and args.type != Fork:
            args.type = Fork

        # Branch is only valid for forked packages
        if args.type != Fork and args.fork_branch:
            raise InvalidArgumentsError(
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
        if existing_package := next((p for p in packages if p.same(package)), None):
            if update:
                # Remove old version of the package
                packages = [p for p in packages if p == existing_package]
            else:
                raise DuplicatePackageError("Package already exists in the list")

        package.install(self.hass_config)

        packages.append(package)
        self.write_lock_packages(packages)

    def upgrade_packages(self, package_names: list[str], yes: bool = False):
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

        confirmed = yes or input("Upgrade all packages? (y/N) ").lower() == "y"
        if outdated_packages and not confirmed:
            return

        for installed_package in outdated_packages:
            installed_package.install(self.hass_config)

        # Update lock file to latest now that we know they are uograded
        latest_lookup = {p: p for p in latest_packages}
        packages = [latest_lookup.get(p, p) for p in self.read_lock_packages()]

        self.write_lock_packages(packages)

    def list_packages(self, verbose: bool = False, freeze: bool = False):
        """List installed packages and their versions."""
        installed_packages = get_installed_packages()
        for package in installed_packages:
            print(package.verbose_str() if verbose else str(package))

        if freeze:
            self.write_lock_packages(installed_packages)

    def list_tags(self, url: str, limit: int = 10):
        print(f"Tags for {url}:")
        for tag in get_repo_tags(url)[-1 * limit :]:
            print(tag)

    def remove_packages(self, package_names: list[str], yes: bool = False):
        """Remove installed packages and uodate lock."""
        packages_to_remove = [
            package
            for package in get_installed_packages()
            if (
                package.name in package_names
                or package.url in package_names
                or (
                    hasattr(package, "fork_component")
                    and getattr(package, "fork_component") in package_names
                )
            )
        ]

        if package_names and not packages_to_remove:
            print("No packages found to remove")
            return

        print("Packages to remove:")
        for package in packages_to_remove:
            print(package)

        confirmed = yes or input("Remove listed packages? (y/N) ").lower() == "y"
        if packages_to_remove and not confirmed:
            return

        remaining_packages = [
            package
            for package in self.read_lock_packages()
            if package not in packages_to_remove
        ]

        for package in packages_to_remove:
            package.uninstall(self.hass_config)

        self.write_lock_packages(remaining_packages)


def args_to_package(args) -> Package:
    ignore_versions = (
        {version for version in args.ignore_versions.split(",")}
        if args.ignore_versions
        else None
    )

    if args.type == Fork:
        if not args.fork_branch:
            raise InvalidArgumentsError(
                "A branch must be provided for forked components"
            )
        if not args.fork_component:
            raise InvalidArgumentsError(
                "A component must be provided for forked components"
            )

        return Fork(
            args.url,
            branch_name=args.fork_branch,
            fork_component=args.fork_component,
            version=args.version,
            ignored_versions=ignore_versions,
        )

    return args.type(args.url, version=args.version, ignored_versions=ignore_versions)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

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
            try:
                new_package = args_to_package(args)
            except InvalidArgumentsError as e:
                print(e)
                return 1
            try:
                unhacs.add_package(
                    new_package,
                    update=args.update,
                )
            except DuplicatePackageError as e:
                print(e)
                return 1
        else:
            print("Either a file or a URL must be provided")
            return 1
    elif args.subcommand == "list":
        unhacs.list_packages(args.verbose, args.freeze)
    elif args.subcommand == "tags":
        unhacs.list_tags(args.url, limit=args.limit)
    elif args.subcommand == "remove":
        unhacs.remove_packages(args.packages, yes=args.yes)
    elif args.subcommand == "upgrade":
        unhacs.upgrade_packages(args.packages, yes=args.yes)
    else:
        print(f"Command {args.subcommand} is not implemented")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
