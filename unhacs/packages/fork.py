import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests

from unhacs.git import get_branch_zip
from unhacs.git import get_latest_sha
from unhacs.packages import PackageType
from unhacs.packages.integration import Integration
from unhacs.utils import extract_zip


class Fork(Integration):
    other_fields = ["fork_component", "branch_name"]
    package_type = PackageType.FORK

    def __init__(
        self,
        url: str,
        fork_component: str,
        branch_name: str,
        version: str | None = None,
        ignored_versions: set[str] | None = None,
    ):
        self.fork_component = fork_component
        self.branch_name = branch_name

        super().__init__(
            url,
            version=version,
            ignored_versions=ignored_versions,
        )

    def __str__(self):
        return f"{self.package_type}: {self.fork_component} ({self.owner}/{self.name}@{self.branch_name}) {self.version}"

    def fetch_version_release(self, version: str | None = None) -> str:
        return get_latest_sha(self.url, self.branch_name)

    def install(self, hass_config_path: Path) -> None:
        """Installs the integration from hass fork."""
        zipball_url = get_branch_zip(self.url, self.branch_name)
        response = requests.get(zipball_url)
        response.raise_for_status()

        with tempfile.TemporaryDirectory(prefix="unhacs-") as tempdir:
            tmpdir = Path(tempdir)
            extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

            source, dest = None, None
            source = tmpdir / "homeassistant" / "components" / self.fork_component
            if not source.exists() or not source.is_dir():
                raise ValueError(
                    f"Could not find {self.fork_component} in {self.url}@{self.version}"
                )

            # Add version to manifest
            manifest_file = source / "manifest.json"
            manifest = json.load(manifest_file.open())
            manifest["version"] = "0.0.0"
            json.dump(manifest, manifest_file.open("w"))

            dest = self.get_install_dir(hass_config_path) / source.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(source, dest)

            self.to_yaml(dest.joinpath("unhacs.yaml"))
