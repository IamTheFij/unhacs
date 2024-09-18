import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests
import yaml

from unhacs.git import get_tag_zip
from unhacs.packages import Package
from unhacs.packages import PackageType
from unhacs.utils import extract_zip


class Integration(Package):
    package_type = PackageType.INTEGRATION

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
        return hass_config_path / "custom_components"

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list[Package]:
        packages: list[Package] = []

        for custom_component in cls.get_install_dir(hass_config_path).glob("*"):
            unhacs = custom_component / "unhacs.yaml"
            if unhacs.exists():
                data = yaml.safe_load(unhacs.read_text())
                if data["package_type"] == "fork":
                    continue
                package = cls.from_yaml(data)
                package.path = custom_component
                packages.append(package)

        return packages

    def install(self, hass_config_path: Path) -> None:
        """Installs the integration package."""
        zipball_url = get_tag_zip(self.url, self.version)
        response = requests.get(zipball_url)
        response.raise_for_status()

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            source, dest = None, None
            for custom_component in tmpdir.glob("custom_components/*"):
                source = custom_component
                dest = self.get_install_dir(hass_config_path) / custom_component.name
                break
            else:
                hacs_json = json.loads((tmpdir / "hacs.json").read_text())
                if hacs_json.get("content_in_root"):
                    source = tmpdir
                    dest = self.get_install_dir(hass_config_path) / self.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(source, dest)
            self.path = dest

            self.to_yaml(self.unhacs_path)
