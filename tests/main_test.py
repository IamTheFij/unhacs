import os
import shutil
import tempfile
import unittest
from pathlib import Path

from unhacs.main import main
from unhacs.packages import get_installed_packages

INTEGRATION_URL = "https://github.com/simbaja/ha_gehome"
INTEGRATION_VERSION = "v0.6.9"

PLUGIN_URL = "https://github.com/kalkih/mini-media-player"
PLUGIN_VERSION = "v1.16.8"

THEME_URL = "https://github.com/basnijholt/lovelace-ios-themes"
THEME_VERSION = "v3.0.1"

FORK_URL = "https://github.com/ViViDboarder/home-assistant"
FORK_BRANCH = "dev"
FORK_COMPONENT = "nextbus"
FORK_VERSION = "3b2893f2f4e16f9a05d9cc4a7ba9f31984c841be"


class TestMainIntegrarion(unittest.TestCase):
    test_dir: str

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        pass

    def run_itest(
        self,
        test_name: str,
        command: str,
        expected_files: list[str] | None = None,
        expect_missing_files: list[str] | None = None,
        expected_code: int = 0,
    ):
        with self.subTest(test_name, command=command):
            self.assertEqual(main(command.split()), expected_code)

            # Verify that the package was installed by checking the filesystem
            if expected_files:
                expected_files = [
                    os.path.join(self.test_dir, file) for file in expected_files
                ]
                missing_files = [
                    file for file in expected_files if not os.path.exists(file)
                ]
                if missing_files:
                    self.fail(f"Missing files: {missing_files}")

            if expect_missing_files:
                expect_missing_files = [
                    os.path.join(self.test_dir, file) for file in expect_missing_files
                ]
                existing_files = [
                    file for file in expect_missing_files if os.path.exists(file)
                ]
                if existing_files:
                    self.fail(f"Files should not exist: {existing_files}")

    def test_integration(self):
        self.run_itest(
            "Add integration",
            f"add {INTEGRATION_URL} --version {INTEGRATION_VERSION}",
            expected_files=[
                "custom_components/ge_home/__init__.py",
                "custom_components/ge_home/manifest.json",
                "custom_components/ge_home/switch.py",
            ],
        )

        self.run_itest(
            "List installed packages",
            "list",
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, INTEGRATION_URL)
        self.assertEqual(installed[0].version, INTEGRATION_VERSION)

        self.run_itest(
            "Double add",
            f"add {INTEGRATION_URL}",
            expected_code=1,
        )

        self.run_itest(
            "Upgrade to latest version",
            "upgrade ha_gehome --yes",
            expected_files=[
                "custom_components/ge_home/__init__.py",
                "custom_components/ge_home/manifest.json",
                "custom_components/ge_home/switch.py",
            ],
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, INTEGRATION_URL)
        self.assertNotEqual(installed[0].version, INTEGRATION_VERSION)

        self.run_itest(
            "Downgrade integration",
            f"add {INTEGRATION_URL} --version {INTEGRATION_VERSION} --update",
            expected_files=[
                "custom_components/ge_home/__init__.py",
                "custom_components/ge_home/manifest.json",
                "custom_components/ge_home/switch.py",
            ],
        )

        self.run_itest(
            "List installed packages",
            "list",
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, INTEGRATION_URL)
        self.assertEqual(installed[0].version, INTEGRATION_VERSION)

        self.run_itest(
            "Remove integration",
            "remove ha_gehome --yes",
            expect_missing_files=[
                "custom_components/ge_home/__init__.py",
                "custom_components/ge_home/manifest.json",
                "custom_components/ge_home/switch.py",
            ],
        )

        installed = get_installed_packages()
        self.assertEqual(len(installed), 0)

    def test_plugin(self):
        self.run_itest(
            "Add plugin",
            f"add --plugin {PLUGIN_URL} --version {PLUGIN_VERSION}",
            expected_files=[
                "www/js/mini-media-player-bundle.js",
            ],
        )

        self.run_itest(
            "List installed packages",
            "list",
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, PLUGIN_URL)
        self.assertEqual(installed[0].version, PLUGIN_VERSION)

        self.run_itest(
            "Remove plugin",
            "remove mini-media-player --yes",
            expect_missing_files=[
                "www/js/mini-media-player-bundle.js",
            ],
        )

        installed = get_installed_packages()
        self.assertEqual(len(installed), 0)

    def test_theme(self):
        self.run_itest(
            "Add theme",
            f"add --theme {THEME_URL} --version {THEME_VERSION}",
            expected_files=[
                "themes/ios-themes.yaml",
            ],
        )

        self.run_itest(
            "List installed packages",
            "list",
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, THEME_URL)
        self.assertEqual(installed[0].version, THEME_VERSION)

        self.run_itest(
            "Remove theme",
            "remove lovelace-ios-themes --yes",
            expect_missing_files=[
                "themes/ios-themes.yaml",
            ],
        )

        installed = get_installed_packages()
        self.assertEqual(len(installed), 0)

    def test_fork(self):
        self.run_itest(
            "Add fork",
            f"add {FORK_URL} --fork-component {FORK_COMPONENT} --fork-branch {FORK_BRANCH} --version {FORK_VERSION}",
            expected_files=[
                "custom_components/nextbus/__init__.py",
                "custom_components/nextbus/manifest.json",
                "custom_components/nextbus/sensor.py",
                "custom_components/nextbus/unhacs.yaml",
            ],
        )

        self.run_itest(
            "List installed packages",
            "list",
        )
        installed = get_installed_packages()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].url, FORK_URL)
        self.assertEqual(installed[0].version, FORK_VERSION)

        self.run_itest(
            "Remove fork",
            f"remove {FORK_URL} --yes",
            expect_missing_files=[
                "custom_components/nextbus/__init__.py",
                "custom_components/nextbus/manifest.json",
                "custom_components/nextbus/sensor.py",
                "custom_components/nextbus/unhacs.yaml",
            ],
        )

        installed = get_installed_packages()
        self.assertEqual(len(installed), 0)


if __name__ == "__main__":
    unittest.main()
