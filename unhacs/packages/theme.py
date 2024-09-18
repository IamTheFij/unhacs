from pathlib import Path
from typing import cast

import requests

from unhacs.packages import Package
from unhacs.packages import PackageType


class Theme(Package):
    package_type = PackageType.THEME

    def __init__(
        self,
        url: str,
        version: str | None = None,
        ignored_versions: set[str] | None = None,
    ):
        super().__init__(
            url,
            version=version,
            ignored_versions=ignored_versions,
        )

    @classmethod
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        return hass_config_path / "themes"

    @property
    def unhacs_path(self) -> Path | None:
        if self.path is None:
            return None

        return self.path.with_name(f"{self.path.name}.unhacs")

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list["Package"]:
        packages: list[Package] = []

        for js_unhacs in cls.get_install_dir(hass_config_path).glob("*.unhacs"):
            package = cls.from_yaml(js_unhacs)
            package.path = js_unhacs.with_name(js_unhacs.name.removesuffix(".unhacs"))
            packages.append(package)

        return packages

    def install(self, hass_config_path: Path) -> None:
        """Install theme yaml."""
        filename = self.get_hacs_json().get("filename")
        if not filename:
            raise ValueError(f"No filename found for theme {self.name}")

        filename = cast(str, filename)
        url = f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{self.version}/themes/{filename}"
        theme = requests.get(url)
        theme.raise_for_status()

        themes_path = self.get_install_dir(hass_config_path)
        themes_path.mkdir(parents=True, exist_ok=True)
        self.path = themes_path.joinpath(filename)
        self.path.write_text(theme.text)

        self.to_yaml(self.unhacs_path)
