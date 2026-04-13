from pathlib import Path
from typing import override

import requests

from unhacs.packages.common import Package
from unhacs.packages.common import PackageType


class Plugin(Package):
    package_type: PackageType = PackageType.PLUGIN

    @override
    @classmethod
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        return hass_config_path / "www" / "js"

    @override
    @classmethod
    def path_to_unhacs(cls, path: Path) -> Path:
        return path.with_name(f"{path.name}-unhacs.yaml")

    @override
    @classmethod
    def unhacs_to_path(cls, path: Path) -> Path:
        return path.with_name(path.name.removesuffix("-unhacs.yaml"))

    @override
    @classmethod
    def unhacs_glob_pattern(cls) -> str:
        """Returns the glob pattern to find this package's unhacs.yaml file."""
        return "*-unhacs.yaml"

    @override
    def install(self, hass_config_path: Path) -> None:
        """Installs the plugin package."""

        valid_filenames: list[str]
        if filename := self.get_hacs_json().get("filename"):
            valid_filenames = [filename]
        else:
            valid_filenames = [
                f"{self.name.removeprefix('lovelace-')}.js",
                f"{self.name}.js",
                f"{self.name}-umd.js",
                f"{self.name}-bundle.js",
            ]

        def real_get(filename: str) -> requests.Response | None:
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
        self.path: Path | None = js_path.joinpath(filename)

        # Write the plugin file
        _ = self.path.write_text(plugin.text)

        # Write the unhacs file
        _ = self.to_yaml(self.unhacs_path)
