"""Validate upload contents and the password gate without calling itch.io."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "publish_itch.py"
SPEC = importlib.util.spec_from_file_location("publish_itch", SCRIPT)
publish = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish
SPEC.loader.exec_module(publish)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dist = Path(self.temp.name)
        self.version = "0.4.2"
        names = publish.artifact_names(self.version)
        portable = self.dist / "ClassicPriceLens-Windows-x64"
        portable.mkdir()
        (portable / "run-windows.bat").write_text("example launcher")
        manifest = {"version": self.version, "files": {"run-windows.bat": publish.digest(portable / "run-windows.bat")}}
        (portable / "build-manifest.json").write_text(json.dumps(manifest))
        with zipfile.ZipFile(self.dist / names["windows-portable"], "w") as archive:
            for path in portable.iterdir():
                archive.write(path, "ClassicPriceLens-Windows-x64/" + path.name)
        for channel, name in names.items():
            if channel != "windows-portable":
                (self.dist / name).write_bytes(channel.encode())
        self.checksums()

    def tearDown(self):
        self.temp.cleanup()

    def checksums(self):
        names = publish.artifact_names(self.version)
        (self.dist / "SHA256SUMS.txt").write_text("".join(publish.digest(self.dist / name) + "  " + name + "\n" for name in names.values()))

    def test_plan_has_five_stable_channels_and_only_release_payloads(self):
        uploads = publish.prepare_uploads(self.dist, self.version)
        self.assertEqual([upload.channel for upload in uploads],
                         ["windows-portable", "windows-installer", "linux-arch", "linux-debian", "checksums"])
        self.assertEqual(uploads[0].source, self.dist / "ClassicPriceLens-Windows-x64")
        names = publish.artifact_names(self.version)
        for upload in uploads[1:]:
            expected = {"INSTALL.txt", "SHA256SUMS.txt"}
            if upload.channel in names:
                expected.add(names[upload.channel])
                self.assertEqual((upload.source / names[upload.channel]).read_bytes(), (self.dist / names[upload.channel]).read_bytes())
            self.assertEqual({path.name for path in upload.source.iterdir()}, expected)
        publish.prepare_uploads(self.dist, self.version)

    def test_corrupted_build_is_rejected_before_staging(self):
        name = publish.artifact_names(self.version)["linux-arch"]
        (self.dist / name).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            publish.prepare_uploads(self.dist, self.version)
        self.assertFalse((self.dist / "itch-staging").exists())

    def test_untracked_portable_file_or_modified_payload_is_rejected(self):
        portable = self.dist / "ClassicPriceLens-Windows-x64"
        extra = portable / "private.sqlite"
        extra.write_bytes(b"private")
        with self.assertRaisesRegex(ValueError, "Unexpected or missing"):
            publish.validate_release(self.dist, self.version)
        extra.unlink()
        (portable / "run-windows.bat").write_text("modified")
        with self.assertRaisesRegex(ValueError, "Portable file checksum mismatch"):
            publish.validate_release(self.dist, self.version)

    def test_mixed_release_versions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly this version"):
            publish.validate_release(self.dist, "0.4.3")

    def test_unknown_staging_files_are_preserved_and_stop_the_upload(self):
        folder = self.dist / "itch-staging" / self.version / "windows-installer"
        folder.mkdir(parents=True)
        extra = folder / "personal.txt"
        extra.write_text("keep")
        with self.assertRaisesRegex(ValueError, "Unexpected files"):
            publish.prepare_uploads(self.dist, self.version)
        self.assertEqual(extra.read_text(), "keep")

    def test_password_gate_requires_the_actual_project_form(self):
        url = publish.project_url(publish.DEFAULT_PROJECT)
        for html, expected in [
            ('<form method="post" action="/classic-price-lens/password"><input type="password" name="game_password"></form>', True),
            ('<form method="post" action="https://elsewhere.example/password"><input type="password" name="game_password"></form>', False),
            ('<form method="post" action="/login"><input type="password" name="password"></form>', False),
            ('<p>A password is required</p>', False),
        ]:
            with self.subTest(html=html):
                page = publish.PasswordGate(url)
                page.feed(html)
                self.assertEqual(page.protected, expected)

    def test_push_uses_argument_arrays_and_same_channel_with_release_version(self):
        upload = publish.Upload("linux-debian", Path("folder with spaces"))
        command = publish.push_command("butler", upload, publish.DEFAULT_PROJECT, self.version)
        self.assertEqual(command, ["butler", "push", "folder with spaces", "zhuffman68/classic-price-lens:linux-debian",
                                   "--userversion", "0.4.2", "--if-changed"])


if __name__ == "__main__":
    unittest.main()
