import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from typing import cast
from typing import override
from zipfile import ZipFile

import requests
import yaml

from unhacs.git import get_tag_zip
from unhacs.packages.common import Package
from unhacs.packages.common import PackageType
from unhacs.utils import extract_zip


class Integration(Package):
    package_type: PackageType = PackageType.INTEGRATION

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
    @override
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        return hass_config_path / "custom_components"

    @classmethod
    @override
    def find_installed(cls, hass_config_path: Path) -> list[Package]:
        packages: list[Package] = []

        for custom_component in cls.get_install_dir(hass_config_path).glob("*"):
            unhacs = custom_component / "unhacs.yaml"
            if unhacs.exists():
                data = cast(dict[str, Any], yaml.safe_load(unhacs.read_text()))
                if data["package_type"] == "fork":
                    continue
                package = cls.from_yaml(data)
                package.path = custom_component
                packages.append(package)

        return packages

    @override
    def install(self, hass_config_path: Path) -> None:
        """Installs the integration package."""
        zipball_url = get_tag_zip(self.url, self.version)
        response = requests.get(zipball_url)
        response.raise_for_status()

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            _ = extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            source, dest = None, None
            for custom_component in tmpdir.glob("custom_components/*"):
                if (
                    custom_component.is_dir()
                    and (custom_component / "manifest.json").exists()
                ):
                    source = custom_component
                    dest = (
                        self.get_install_dir(hass_config_path) / custom_component.name
                    )
                    break
            else:
                hacs_json = cast(
                    dict[str, Any], json.loads((tmpdir / "hacs.json").read_text())
                )
                if hacs_json.get("content_in_root"):
                    source = tmpdir
                    dest = self.get_install_dir(hass_config_path) / self.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            _ = shutil.move(source, dest)

            self.path: Path | None = dest

            _ = self.to_yaml(self.unhacs_path)
