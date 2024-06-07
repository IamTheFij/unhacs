from dataclasses import dataclass
from pathlib import Path

DEFAULT_PACKAGE_FILE = "unhacs.txt"


@dataclass
class Package:
    url: str
    version: str
    name: str

    def __str__(self):
        return f"{self.name} {self.version}"

    def verbose_str(self):
        return f"{self.name} {self.version} ({self.url})"


# Read a list of Packages from a text file in the plain text format "URL version name"
def read_packages(package_file: str = DEFAULT_PACKAGE_FILE) -> list[Package]:
    path = Path(package_file)
    if path.exists():
        with path.open() as f:
            return [Package(*line.strip().split()) for line in f]
    return []


# Write a list of Packages to a text file in the format URL version name
def write_packages(packages: list[Package], package_file: str = DEFAULT_PACKAGE_FILE):
    with open(package_file, "w") as f:
        for package in packages:
            f.write(f"{package.url} {package.version} {package.name}\n")
