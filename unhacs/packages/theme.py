from pathlib import Path
from typing import override

import requests

from unhacs.packages.common import Package
from unhacs.packages.common import PackageType


class Theme(Package):
    package_type: PackageType = PackageType.THEME

    @classmethod
    @override
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        return hass_config_path / "themes"

    @classmethod
    @override
    def path_to_unhacs(cls, path: Path) -> Path:
        return path.with_name(f"{path.name}.unhacs")

    @override
    @classmethod
    def unhacs_to_path(cls, path: Path) -> Path:
        return path.with_name(path.name.removesuffix(".unhacs"))

    @override
    @classmethod
    def unhacs_glob_pattern(cls) -> str:
        """Returns the glob pattern to find this package's unhacs.yaml file."""
        return "*.unhacs"

    @override
    def install(self, hass_config_path: Path) -> None:
        """Install theme yaml."""
        filename = self.get_hacs_json().get("filename")
        if not filename:
            raise ValueError(f"No filename found for theme {self.name}")

        filename = filename
        url = f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{self.version}/themes/{filename}"
        theme = requests.get(url)
        theme.raise_for_status()

        themes_path = self.get_install_dir(hass_config_path)
        themes_path.mkdir(parents=True, exist_ok=True)
        self.path: Path | None = themes_path.joinpath(filename)

        # Write the theme file
        _ = self.path.write_text(theme.text)

        # Write the unhacs file
        _ = self.to_yaml(self.unhacs_path)
