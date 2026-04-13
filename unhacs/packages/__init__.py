from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict
from typing import cast

import yaml

from unhacs.packages.common import Package
from unhacs.packages.common import PackageDict
from unhacs.packages.common import PackageType
from unhacs.packages.fork import Fork
from unhacs.packages.integration import Integration
from unhacs.packages.plugin import Plugin
from unhacs.packages.theme import Theme
from unhacs.utils import DEFAULT_HASS_CONFIG_PATH
from unhacs.utils import DEFAULT_PACKAGE_FILE

PACKAGE_TYPE_TO_CLS: dict[PackageType, type[Package]] = {
    PackageType.INTEGRATION: Integration,
    PackageType.PLUGIN: Plugin,
    PackageType.THEME: Theme,
    PackageType.FORK: Fork,
}


class PackageLock(TypedDict):
    packages: list[PackageDict]


def package_factory(data: PackageDict | Path | str) -> Package:
    if not isinstance(data, dict):
        data = cast(PackageDict, yaml.safe_load(open(data)))

    # Convert package_type to enum
    package_type = PackageType(data["package_type"])

    return PACKAGE_TYPE_TO_CLS[package_type].from_dict(data)


def get_installed_packages(
    hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH,
    package_types: Iterable[PackageType] | None = None,
) -> list[Package]:
    # Integration packages
    packages: list[Package] = []

    if package_types is None:
        package_types = PACKAGE_TYPE_TO_CLS.keys()

    for package_type in package_types:
        packages += PACKAGE_TYPE_TO_CLS[package_type].find_installed(hass_config_path)

    return packages


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_lock_packages(package_file: Path = DEFAULT_PACKAGE_FILE) -> list[Package]:
    if package_file.exists():
        package_lock = cast(PackageLock, yaml.safe_load(package_file.open()))
        if "packages" not in package_lock:
            raise ValueError("Malformed unhacs.yaml lock file")

        return [package_factory(p) for p in package_lock["packages"]]

    return []


# Write a list of Packages to a text file in the format URL version name
def write_lock_packages(
    packages: Iterable[Package], package_file: Path = DEFAULT_PACKAGE_FILE
):
    package_data = {"packages": [p.to_dict() for p in packages]}
    with open(package_file, "w") as f:
        yaml.dump(package_data, f)
