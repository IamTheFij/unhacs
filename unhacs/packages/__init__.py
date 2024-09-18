from collections.abc import Iterable
from pathlib import Path
from typing import cast

import yaml

from unhacs.packages.common import Package
from unhacs.packages.common import PackageType
from unhacs.packages.fork import Fork
from unhacs.packages.integration import Integration
from unhacs.packages.plugin import Plugin
from unhacs.packages.theme import Theme
from unhacs.utils import DEFAULT_HASS_CONFIG_PATH
from unhacs.utils import DEFAULT_PACKAGE_FILE


def from_yaml(data: dict | Path | str) -> Package:
    if isinstance(data, Path):
        data = yaml.safe_load(data.open())
    elif isinstance(data, str):
        data = yaml.safe_load(data)

    data = cast(dict, data)

    # Convert package_type to enum
    package_type = data.pop("package_type", None)
    if package_type and isinstance(package_type, str):
        package_type = PackageType(package_type)

    url = data.pop("url")

    return {
        PackageType.INTEGRATION: Integration,
        PackageType.PLUGIN: Plugin,
        PackageType.THEME: Theme,
        PackageType.FORK: Fork,
    }[package_type](url, **data)


def get_installed_packages(
    hass_config_path: Path = DEFAULT_HASS_CONFIG_PATH,
    package_types: Iterable[PackageType] = (
        PackageType.INTEGRATION,
        PackageType.FORK,
        PackageType.PLUGIN,
        PackageType.THEME,
    ),
) -> list[Package]:
    # Integration packages
    packages: list[Package] = []

    if PackageType.INTEGRATION in package_types:
        packages.extend(Integration.find_installed(hass_config_path))

    if PackageType.FORK in package_types:
        packages.extend(Fork.find_installed(hass_config_path))

    # Plugin packages
    if PackageType.PLUGIN in package_types:
        packages.extend(Plugin.find_installed(hass_config_path))

    # Theme packages
    if PackageType.THEME in package_types:
        packages.extend(Theme.find_installed(hass_config_path))

    return packages


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_lock_packages(package_file: Path = DEFAULT_PACKAGE_FILE) -> list[Package]:
    if package_file.exists():
        with package_file.open() as f:
            return [from_yaml(p) for p in yaml.safe_load(f)["packages"]]
    return []


# Write a list of Packages to a text file in the format URL version name
def write_lock_packages(
    packages: Iterable[Package], package_file: Path = DEFAULT_PACKAGE_FILE
):
    with open(package_file, "w") as f:
        yaml.dump({"packages": [p.to_yaml() for p in packages]}, f)
