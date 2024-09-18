from pathlib import Path
from zipfile import ZipFile

DEFAULT_HASS_CONFIG_PATH: Path = Path(".")
DEFAULT_PACKAGE_FILE = Path("unhacs.yaml")


def extract_zip(zip_file: ZipFile, dest_dir: Path) -> Path:
    """Extract a zip file to a directory."""
    for info in zip_file.infolist():
        if info.is_dir():
            continue
        file = Path(info.filename)
        # Strip top directory from path
        file = Path(*file.parts[1:])
        path = dest_dir / file
        path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(info) as source, open(path, "wb") as dest:
            dest.write(source.read())

    return dest_dir
