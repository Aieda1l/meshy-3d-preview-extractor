#!/usr/bin/env python3
"""Capture 3D files requested by a browser preview you can access."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

MODEL_EXTENSIONS = {
    ".glb", ".gltf", ".obj", ".stl", ".ply", ".fbx",
    ".3mf", ".usdz", ".usd", ".usda", ".usdc", ".bin", ".zip",
}
TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ktx2", ".basis", ".avif"}
MODEL_MIMES = {
    "application/octet-stream", "application/x-binary", "application/zip",
    "application/x-3mf", "model/gltf-binary", "model/gltf+json",
    "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
}
DEFAULT_MESHY_URL = "https://www.meshy.ai/"


def safe_file_name(name: str) -> str:
    """Strip path components and characters unsafe for a local file name."""
    name = unquote(name).replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:85].strip("._") or "model_asset"


def classify_asset(data: bytes, suffix: str, mime: str, *, textures: bool) -> str | None:
    """Return a likely file extension, or None for irrelevant responses."""
    if not data:
        return None
    if data.startswith(b"glTF"):
        return ".glb"
    if data.startswith(b"Kaydara FBX Binary"):
        return ".fbx"
    if data.startswith((b"ply\n", b"ply\r\n")):
        return ".ply"
    if data.startswith(b"\xabKTX 20\xbb\r\n\x1a\n") and textures:
        return ".ktx2"
    if data.startswith(b"PK\x03\x04") and suffix in {".3mf", ".usdz", ".zip"}:
        return suffix
    if data.startswith(b"PK\x03\x04") and mime == "application/zip":
        return ".zip"
    if suffix == ".gltf" or mime == "model/gltf+json":
        try:
            obj = json.loads(data)
            if isinstance(obj, dict) and isinstance(obj.get("asset"), dict) and "version" in obj["asset"]:
                return ".gltf"
        except (ValueError, UnicodeDecodeError):
            pass
        return None
    # Error pages sometimes masquerade as model or octet-stream responses.
    prefix = data.lstrip()[:100].lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"{")):
        return None
    if suffix in {".obj", ".stl", ".fbx", ".usd", ".usda", ".usdc", ".bin"}:
        return suffix
    if suffix in TEXTURE_EXTENSIONS and textures:
        return suffix
    if data[:6].lower() == b"solid " and b"facet" in data[:1024]:
        return ".stl"
    if len(data) >= 84 and (84 + 50 * int.from_bytes(data[80:84], "little")) == len(data):
        return ".stl"
    if data.startswith((b"v ", b"# ")) and b"\nf " in data[:100000]:
        return ".obj"
    if mime in {"application/octet-stream", "application/x-binary"} and len(data) >= 256:
        return ".bin"
    return None


def preview_url(value: str) -> str:
    """Normalize a pasted preview URL to http(s)."""
    value = value.strip()
    if not value:
        return DEFAULT_MESHY_URL
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid http(s) preview URL.")
    return value


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter a positive whole number.") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive whole number.")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save model assets loaded in a Meshy (or other) web preview.",
        epilog="Run without a URL to paste one interactively.",
    )
    parser.add_argument("url", nargs="?", help="Preview URL (optional)")
    parser.add_argument("--out", default="captured_3d", help="Output folder (default: captured_3d)")
    parser.add_argument("--profile", default=".preview_browser_profile", help="Persistent browser login folder")
    parser.add_argument("--textures", action="store_true", help="Include texture image responses")
    parser.add_argument("--max-mb", type=positive_int, default=400, help="Maximum size per response in MB (default: 400)")
    parser.add_argument("--chromium-path", help="Path to an installed Chrome/Chromium executable")
    args = parser.parse_args(argv)
    if args.url:
        try:
            args.url = preview_url(args.url)
        except ValueError as exc:
            parser.error(str(exc))
    return args


class CaptureSession:
    """Track downloaded files, network assets and their metadata."""

    def __init__(self, output: Path, *, textures: bool, max_bytes: int):
        self.output = output
        self.assets_dir = output / "assets"
        self.downloads_dir = output / "downloads"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.textures = textures
        self.max_bytes = max_bytes
        self.assets: list[dict] = []
        self.downloads: list[dict] = []
        self.seen_hashes: set[str] = set()
        self.tasks: set[asyncio.Task] = set()
        self.download_lock = asyncio.Lock()

    def schedule(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def capture_response(self, response) -> None:
        try:
            if not 200 <= response.status < 300:
                return
            parsed = urlsplit(response.url)
            suffix = Path(parsed.path).suffix.lower()
            mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            model_hint = suffix in MODEL_EXTENSIONS or mime in MODEL_MIMES or mime.startswith("model/")
            texture_hint = self.textures and (suffix in TEXTURE_EXTENSIONS or mime.startswith("image/"))
            if not (model_hint or texture_hint):
                return
            length = response.headers.get("content-length", "")
            if length.isdigit() and int(length) > self.max_bytes:
                print(f"  Skipped large response: {parsed.path}")
                return
            data = await response.body()
            if len(data) > self.max_bytes:
                print(f"  Skipped large response: {parsed.path}")
                return
            extension = classify_asset(data, suffix, mime, textures=self.textures)
            if not extension:
                return
            digest = hashlib.sha256(data).hexdigest()
            if digest in self.seen_hashes:
                return
            self.seen_hashes.add(digest)
            name = f"{safe_file_name(Path(parsed.path).stem)}_{digest[:12]}{extension}"
            (self.assets_dir / name).write_bytes(data)
            self.assets.append({
                "file": f"assets/{name}", "sha256": digest, "bytes": len(data),
                "type": mime, "source_host": parsed.hostname,
            })
            print(f"  Saved network asset: {name} ({len(data):,} bytes)")
        except Exception as exc:
            print(f"  Capture warning: {type(exc).__name__}: {exc}")

    async def save_download(self, download) -> None:
        try:
            async with self.download_lock:
                safe_name = safe_file_name(download.suggested_filename)
                destination = self.downloads_dir / safe_name
                index = 2
                while destination.exists():
                    destination = self.downloads_dir / f"{Path(safe_name).stem}_{index}{Path(safe_name).suffix}"
                    index += 1
                await download.save_as(str(destination))
                self.downloads.append({
                    "file": f"downloads/{destination.name}", "bytes": destination.stat().st_size,
                })
                print(f"  Saved browser download: {destination.name}")
        except Exception as exc:
            print(f"  Download warning: {type(exc).__name__}: {exc}")

    async def finish(self) -> Path:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        path = self.output / "manifest.json"
        path.write_text(json.dumps({
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "asset_count": len(self.assets), "download_count": len(self.downloads),
            "assets": self.assets, "downloads": self.downloads,
        }, indent=2), encoding="utf-8")
        return path


async def run(args: argparse.Namespace) -> int:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright is missing. Run: python -m pip install -r requirements.txt")
        return 1

    output = Path(args.out).expanduser().resolve()
    profile = Path(args.profile).expanduser().resolve()
    session = CaptureSession(output, textures=args.textures, max_bytes=args.max_mb * 1024 * 1024)
    print("\nMeshy 3D Preview Extractor\n")
    print("1. Sign in to Meshy in the browser window if needed.")
    print("2. Open the model preview or refresh it to load the model files.")
    print("3. Use the website's Download button if available.")
    print("4. Press Enter here to finish and see what was saved.\n")
    print(f"Output folder: {output}")
    if args.textures:
        print("Texture capture: enabled")

    async with async_playwright() as playwright:
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile), headless=False, accept_downloads=True,
                viewport={"width": 1440, "height": 900}, executable_path=args.chromium_path,
            )
        except PlaywrightError as exc:
            print(f"\nCould not open Chromium: {exc}")
            print("Try: python -m playwright install chromium")
            print("Close any other extractor instance using the same login profile.")
            return 1

        def watch_page(page) -> None:
            page.on("download", lambda download: session.schedule(session.save_download(download)))

        context.on("response", lambda response: session.schedule(session.capture_response(response)))
        context.on("page", watch_page)
        for existing in context.pages:
            watch_page(existing)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
            except PlaywrightError as exc:
                print(f"  Page couldn't load automatically: {exc}")
                print("  Open the preview manually in the browser instead.")
            try:
                await asyncio.to_thread(input, "\nPress Enter when you are done capturing... ")
            except EOFError:
                print("\nInput closed; saving what was captured.")
        finally:
            await session.finish()
            await context.close()

    print(f"\nDone! {len(session.assets)} network asset(s) and {len(session.downloads)} download(s).")
    print(f"Files and manifest: {output}")
    if not session.assets and not session.downloads:
        print("No model files detected. Try refreshing the preview while the browser is open,")
        print("or use the website's model Download button.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.url is None:
        try:
            args.url = preview_url(input("Paste a Meshy preview URL (Enter opens Meshy): "))
        except (EOFError, KeyboardInterrupt):
            print("\nNo URL provided. Exiting.")
            return 1
        except ValueError as exc:
            print(f"Invalid URL: {exc}")
            return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nCapture interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
