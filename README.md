# Meshy 3D Preview Extractor

Python tool for saving **3D model files loaded by a Meshy preview** or another web-based 3D viewer. It opens Chromium so you can sign in and browse normally while the tool captures network model assets and browser downloads.

**Use it only for models you own or have permission to save.** It doesn't bypass account restrictions, unlock paid exports or reconstruct GPU-only geometry.

## Quick start

Requires **Python 3.10+** and an internet connection for the initial browser installation.

1. Download or clone this repository.
2. Install dependencies in the project folder:

   ```bash
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```

   On Windows, you can double-click **`Install Requirements.bat`** instead.

3. Start the extractor:

   ```bash
   python capture_preview.py
   ```

   On Windows, you can also double-click **`Start Extractor.bat`** after setup.

4. Paste a Meshy preview URL, or press Enter to open Meshy and navigate there yourself.
5. Sign in if needed, open a model preview and **refresh the page if the model was already loaded**. Use the website's Download button if available.
6. Return to the terminal and press **Enter once** to write the manifest and close Chromium.

Captured files are saved in `captured_3d/`. Browser login data lives in `.preview_browser_profile/`; **never upload or share this folder**.

## Options

You can pass a link directly:

```bash
python capture_preview.py "https://www.meshy.ai/"
```

| Argument | What it does |
| --- | --- |
| `--textures` | Also capture image textures (`.png`, `.jpg`, `.webp`, etc.). |
| `--out my_models` | Choose a different output directory. |
| `--max-mb 800` | Increase the maximum per-response size from 400 MB. |
| `--profile my_profile` | Select a different persistent browser login directory. |
| `--chromium-path PATH` | Use an installed Chrome/Chromium executable. |
| `--help` | Show all options. |

## Output

```text
captured_3d/
  assets/         Model and texture responses observed over HTTP
  downloads/      Files saved with the browser's Download button
  manifest.json   File sizes, hashes and source hostnames
```

Supported common formats: **GLB, glTF, OBJ, STL, PLY, FBX, 3MF, USD/USDZ, BIN and ZIP**. The tool saves files returned by the site and does **not** convert formats. Duplicate network assets are deduplicated by SHA-256. Query strings, cookies and request headers aren't recorded in the manifest.

## Troubleshooting

**No files saved?** Start the tool before loading the model, and refresh the preview while Chromium is open. Some previews load data from the cache, WebSockets or unsupported formats. Use an authorized model export/download option on the site when available.

**Chromium won't open?** Run `python -m playwright install chromium`. Close any other extractor using the same browser profile.

**Missing textures or a model that won't open?** Some previews use separate `.gltf`, `.bin` and image files. Try `--textures`. Network assets receive hashed filenames, so paths inside a glTF may need adjusting. A complete native site export is preferable when offered.

**Large models?** Use `--max-mb 800` (or more). Responses without a `Content-Length` header can still be read into memory before the limit is enforced.

This Python tool performs browser network capture. The previous standalone JavaScript scene exporter was removed because it was unreliable. Geometry that never appears in a downloadable HTTP resource cannot be extracted by this tool.

## Privacy and responsible use

Your browser profile stores login cookies, and the output directory can contain private or licensed models. Both are ignored by Git. Review files before sharing them, and respect Meshy's terms and applicable model licensing.

## Test

```bash
python -m unittest discover -s tests -v
```
