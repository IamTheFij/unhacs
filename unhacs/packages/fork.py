import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests
import yaml

from unhacs.git import get_branch_zip
from unhacs.git import get_latest_sha
from unhacs.git import get_sha_zip
from unhacs.packages import PackageType
from unhacs.packages.common import Package
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
        if version:
            return version

        return get_latest_sha(self.url, self.branch_name)

    @classmethod
    def find_installed(cls, hass_config_path: Path) -> list[Package]:
        packages: list[Package] = []

        for custom_component in cls.get_install_dir(hass_config_path).glob("*"):
            unhacs = custom_component / "unhacs.yaml"
            if unhacs.exists():
                data = yaml.safe_load(unhacs.read_text())
                if data["package_type"] != "fork":
                    continue
                package = cls.from_yaml(data)
                package.path = custom_component
                packages.append(package)

        return packages

    def install(self, hass_config_path: Path) -> None:
        """Installs the integration from hass fork."""
        if self.version:
            zipball_url = get_sha_zip(self.url, self.version)
        else:
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
            manifest: dict[str, str]
            with manifest_file.open("r") as f:
                manifest = json.load(f)
                manifest["version"] = "0.0.0"
            with manifest_file.open("w") as f:
                json.dump(manifest, f)

            dest = self.get_install_dir(hass_config_path) / source.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(source, dest)
            self.path = dest

            self.to_yaml(self.unhacs_path)
