import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = self.root / "ccbot.service"
        (self.root / "venv/bin").mkdir(parents=True)
        (self.root / "bin").mkdir()
        for command, stub in (
            ("venv/bin/pip", "#!/bin/sh\nexit 0\n"),
            ("bin/systemctl", '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CCBOT_TEST_COMMANDS"\n'),
        ):
            path = self.root / command
            path.write_text(stub)
            path.chmod(0o755)

        # Relocate system paths so the real installer can run without touching the host.
        script = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        for original, replacement in {
            "/opt/ccbot": self.root / "venv",
            "/etc/systemd/system/ccbot.service": self.service,
            "/etc/logrotate.d/ccbot": self.root / "logrotate",
        }.items():
            script = script.replace(original, str(replacement))
        self.script = self.root / "install.sh"
        self.script.write_text(script)

    def run_installer(self, *args, webhook=None):
        environment = dict(os.environ)
        environment["PATH"] = str(self.root / "bin") + os.pathsep + environment["PATH"]
        environment["CCBOT_TEST_COMMANDS"] = str(self.root / "commands.log")
        environment.pop("SLACK_WEBHOOK_URL", None)
        if webhook is not None:
            environment["SLACK_WEBHOOK_URL"] = webhook
        subprocess.run(["bash", str(self.script), *args], env=environment, check=True, capture_output=True)

    def commands(self):
        return (self.root / "commands.log").read_text().splitlines()

    def assert_webhook(self, expected):
        self.assertIn(f"Environment=SLACK_WEBHOOK_URL={expected}\n", self.service.read_text())

    def test_first_install_without_a_webhook_leaves_it_empty(self):
        self.run_installer()
        self.assert_webhook("")

    def test_reinstall_preserves_existing_webhook(self):
        self.run_installer("https://example.test/original")
        (self.root / "commands.log").unlink()
        self.run_installer()
        self.assert_webhook("https://example.test/original")
        self.assertEqual(self.commands(), ["daemon-reload", "enable ccbot", "restart ccbot"])

    def test_reinstall_keeps_environment_lines_verbatim(self):
        for configuration in (
            'Environment="SLACK_WEBHOOK_URL=https://example.test/a?key=1&stream=alerts"',
            "Environment=SLACK_WEBHOOK_URL=https://example.test/a%%2Fb",
            "Environment=HTTPS_PROXY=http://proxy.test SLACK_WEBHOOK_URL=https://example.test/current",
            "Environment=SLACK_WEBHOOK_URL=https://example.test/old\nEnvironment=SLACK_WEBHOOK_URL=https://example.test/current",
            "EnvironmentFile=/etc/ccbot.env",
        ):
            with self.subTest(configuration=configuration):
                self.service.write_text(f"[Service]\nType=simple\n{configuration}\nRestart=always\n")
                self.run_installer()
                self.assertIn(f"\n{configuration}\n", self.service.read_text())
                self.assertIn("\nDynamicUser=yes\n", self.service.read_text())

    def test_explicit_webhooks_escape_systemd_specifiers(self):
        self.run_installer("https://example.test/a%2Fb")
        self.assert_webhook("https://example.test/a%%2Fb")

    def test_install_and_reinstall_restart_the_service(self):
        self.run_installer("https://example.test/original")
        self.run_installer("https://example.test/replacement")
        self.assertEqual(
            self.commands(),
            ["daemon-reload", "enable ccbot", "restart ccbot"] * 2,
        )

    def test_explicit_configuration_overrides_existing_webhook(self):
        self.run_installer("https://example.test/original")
        self.run_installer(webhook="https://example.test/environment")
        self.assert_webhook("https://example.test/environment")
        self.run_installer("https://example.test/argument", webhook="https://example.test/environment")
        self.assert_webhook("https://example.test/argument")
        self.run_installer(webhook="")
        self.assert_webhook("")
