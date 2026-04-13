import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import cast
from typing import override
from zipfile import ZipFile

import requests

from unhacs.git import get_branch_zip
from unhacs.git import get_latest_sha
from unhacs.git import get_sha_zip
from unhacs.packages.common import PackageDict
from unhacs.packages.common import PackageType
from unhacs.packages.integration import Integration
from unhacs.utils import extract_zip


class ForkDict(PackageDict):
    fork_component: str
    branch_name: str


class Fork(Integration):
    package_type: PackageType = PackageType.FORK

    def __init__(
        self,
        url: str,
        fork_component: str,
        branch_name: str,
        version: str | None = None,
        ignored_versions: set[str] | None = None,
    ):
        self.fork_component: str = fork_component
        self.branch_name: str = branch_name

        super().__init__(
            url,
            version=version,
            ignored_versions=ignored_versions,
        )

    @override
    def _to_hashable(self) -> tuple[str, ...]:
        """Convert Package into a hashable tuple."""
        return (
            self.url,
            self.fork_component,
            self.branch_name,
        )

    @override
    def __str__(self):
        return f"{self.package_type}: {self.fork_component} ({self.owner}/{self.name}@{self.branch_name}) {self.version}"

    @override
    def fetch_version_release(self, version: str | None = None) -> str:
        if version:
            return version

        return get_latest_sha(self.url, self.branch_name)

    @classmethod
    @override
    def from_dict(cls, data: PackageDict) -> "Fork":
        data = cast(ForkDict, data)
        return cls(
            data["url"],
            data["fork_component"],
            data["branch_name"],
            version=data.get("version"),
            ignored_versions=data.get("ignored_versions"),
        )

    @override
    def to_dict(self) -> PackageDict:
        data = cast(ForkDict, super().to_dict())
        data["fork_component"] = self.fork_component
        data["branch_name"] = self.branch_name

        return data

    @override
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
            _ = extract_zip(ZipFile(BytesIO(response.content)), tmpdir)

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
                manifest = cast(dict[str, str], json.load(f))
                manifest["version"] = "0.0.0"
            with manifest_file.open("w") as f:
                json.dump(manifest, f)

            dest = self.get_install_dir(hass_config_path) / source.name

            if not source or not dest:
                raise ValueError("No custom_components directory found")

            # Make parent dirs
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Remove target dir
            shutil.rmtree(dest, ignore_errors=True)
            # Replace target dir
            _ = shutil.move(source, dest)

            self.path: Path | None = dest

            _ = self.to_yaml(self.unhacs_path)
