import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import cast
from typing import override
from zipfile import ZipFile

import requests

from unhacs.git import get_tag_zip
from unhacs.packages.common import Package
from unhacs.packages.common import PackageType
from unhacs.utils import extract_zip


class Integration(Package):
    package_type: PackageType = PackageType.INTEGRATION

    @override
    @classmethod
    def get_install_dir(cls, hass_config_path: Path) -> Path:
        return hass_config_path / "custom_components"

    @override
    @classmethod
    def path_to_unhacs(cls, path: Path) -> Path:
        """Get the unhacs path from the Package path."""
        return path / "unhacs.yaml"

    @override
    @classmethod
    def unhacs_to_path(cls, path: Path) -> Path:
        """Get the Plugin path from the Package unhacs path path."""
        return path.parent

    @override
    @classmethod
    def unhacs_glob_pattern(cls) -> str:
        return "*/unhacs.yaml"

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
                    dict[str, str], json.loads((tmpdir / "hacs.json").read_text())
                )
                if hacs_json.get("content_in_root"):
                    source = tmpdir
                    dest = self.get_install_dir(hass_config_path) / self.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            # Write the integration directory
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            _ = shutil.move(source, dest)

            self.path: Path | None = dest

            # Write the unhacs file
            _ = self.to_yaml(self.unhacs_path)
