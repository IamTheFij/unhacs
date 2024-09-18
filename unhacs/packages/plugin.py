from pathlib import Path
from typing import cast

import requests

from unhacs.packages import Package
from unhacs.packages import PackageType


class Plugin(Package):
    package_type = PackageType.PLUGIN

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
        return hass_config_path / "www" / "js"

    @property
    def unhacs_path(self) -> Path | None:
        if self.path is None:
            return None

        return self.path.with_name(f"{self.path.name}-unhacs.yaml")

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list["Package"]:
        packages: list[Package] = []

        for js_unhacs in cls.get_install_dir(hass_config_path).glob("*-unhacs.yaml"):
            package = cls.from_yaml(js_unhacs)
            package.path = js_unhacs.with_name(
                js_unhacs.name.removesuffix("-unhacs.yaml")
            )
            packages.append(package)

        return packages

    def install(self, hass_config_path: Path) -> None:
        """Installs the plugin package."""

        valid_filenames: list[str]
        if filename := self.get_hacs_json().get("filename"):
            valid_filenames = [cast(str, filename)]
        else:
            valid_filenames = [
                f"{self.name.removeprefix('lovelace-')}.js",
                f"{self.name}.js",
                f"{self.name}-umd.js",
                f"{self.name}-bundle.js",
            ]

        def real_get(filename) -> requests.Response | None:
            urls = [
                f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{self.version}/dist/{filename}",
                f"https://github.com/{self.owner}/{self.name}/releases/download/{self.version}/{filename}",
                f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{self.version}/{filename}",
            ]

            for url in urls:
                plugin = requests.get(url)

                if int(plugin.status_code / 100) == 4:
                    continue

                plugin.raise_for_status()

                return plugin

            return None

        for filename in valid_filenames:
            plugin = real_get(filename)
            if plugin:
                break
        else:
            raise ValueError(f"No valid filename found for package {self.name}")

        js_path = self.get_install_dir(hass_config_path)
        js_path.mkdir(parents=True, exist_ok=True)

        self.path = js_path.joinpath(filename)
        self.path.write_text(plugin.text)

        self.to_yaml(self.unhacs_path)
