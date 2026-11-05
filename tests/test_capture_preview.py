"""Tests for file safety, format identification and the capture manifest."""

import json
import tempfile
import unittest
from pathlib import Path

from capture_preview import CaptureSession, classify_asset, preview_url, safe_file_name


class AssetTests(unittest.TestCase):
    def test_safe_filenames(self):
        self.assertEqual(safe_file_name("../../secret.glb"), "secret.glb")
        self.assertEqual(safe_file_name("folder%2Fmodel%20one.glb"), "model_one.glb")
        self.assertEqual(safe_file_name(".."), "model_asset")

    def test_sniffs_model_formats(self):
        self.assertEqual(classify_asset(b"glTF" + bytes(20), "", "application/octet-stream", textures=False), ".glb")
        self.assertEqual(classify_asset(b'{"asset":{"version":"2.0"}}', ".gltf", "", textures=False), ".gltf")

    def test_does_not_save_login_pages_as_models(self):
        self.assertIsNone(classify_asset(b"<html>Login required</html>", ".bin", "application/octet-stream", textures=False))
        self.assertIsNone(classify_asset(b"{}", ".gltf", "", textures=False))

    def test_textures_are_opt_in(self):
        self.assertIsNone(classify_asset(b"image", ".png", "image/png", textures=False))
        self.assertEqual(classify_asset(b"image", ".png", "image/png", textures=True), ".png")

    def test_preview_url(self):
        self.assertEqual(preview_url("meshy.ai/abc"), "https://meshy.ai/abc")
        self.assertEqual(preview_url(""), "https://www.meshy.ai/")
        with self.assertRaises(ValueError):
            preview_url("file:///etc/passwd")


class FakeResponse:
    status = 200
    url = "https://models.example/preview.glb?token=private"
    headers = {"content-type": "model/gltf-binary"}

    async def body(self):
        return b"glTF" + bytes(32)


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_dedup_and_no_credentials_in_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = CaptureSession(Path(tmp), textures=False, max_bytes=1024)
            await session.capture_response(FakeResponse())
            await session.capture_response(FakeResponse())
            manifest = json.loads((await session.finish()).read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_count"], 1)
            self.assertEqual(manifest["download_count"], 0)
            self.assertEqual(manifest["assets"][0]["source_host"], "models.example")
            self.assertNotIn("token", json.dumps(manifest))
            self.assertTrue((Path(tmp) / manifest["assets"][0]["file"]).exists())


if __name__ == "__main__":
    unittest.main()
