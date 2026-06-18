"""
下载所有 TTS 模型文件
  - Piper 西语模型（通过 hf-mirror 镜像直接下载）
  - Kokoro 中文模型的大文件（通过 huggingface_hub 下载）
  - Kokoro 小文件已在 git 仓库中，无需下载

用法：python download_piper_model.py
"""
import os
import sys

MODEL_DIR = os.path.join(os.path.dirname(__file__), "piper_models")
KOKORO_DIR = os.path.join(os.path.dirname(__file__), "kokoro_models")

# ========== Piper 西语模型 ==========
ES_MODELS = [
    ("es_ES-davefx-medium",     "es/es_ES/davefx/medium"),
    ("es_ES-sharvard-medium",   "es/es_ES/sharvard/medium"),
    ("es_MX-claude-high",       "es/es_MX/claude/high"),
    ("es_AR-daniela-high",      "es/es_AR/daniela/high"),
]

MIRRORS = [
    "https://hf-mirror.com/rhasspy/piper-voices/resolve/main",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main",
]

import urllib.request
import ssl


def download_one(url, dest):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"    done ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"    failed: {e}")
        return False


def download_piper():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name, path in ES_MODELS:
        for ext in [".onnx.json", ".onnx"]:
            fn = name + ext
            dest = os.path.join(MODEL_DIR, fn)
            if os.path.exists(dest) and os.path.getsize(dest) > 100:
                print(f"{fn} exists, skipping")
                continue
            print(f"Downloading {fn} ...")
            ok = False
            for mirror in MIRRORS:
                url = f"{mirror}/{path}/{fn}"
                print(f"  trying: {url[:80]}...")
                ok = download_one(url, dest)
                if ok:
                    break
            if not ok:
                print(f"\n  All mirrors failed for {fn}")
                print(f"    {MIRRORS[0]}/{path}/{fn}")
                print(f"  Place at {dest}")


# ========== Kokoro 中文模型（大文件）==========
KOKORO_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
KOKORO_LARGE_FILES = [
    "kokoro-v1_1-zh.pth",
]
KOKORO_VOICES = ["zf_001", "zf_002", "zm_011"]


def download_kokoro():
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("\nhuggingface_hub not installed. Install with: pip install huggingface_hub")
        print("Then re-run this script to download Kokoro model files.")
        return

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.makedirs(KOKORO_DIR, exist_ok=True)
    os.makedirs(os.path.join(KOKORO_DIR, "voices"), exist_ok=True)

    for f in KOKORO_LARGE_FILES:
        dest = os.path.join(KOKORO_DIR, f)
        if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
            print(f"kokoro {f} exists, skipping")
            continue
        print(f"Downloading kokoro {f} (~320MB)...")
        try:
            hf_hub_download(KOKORO_REPO, f, local_dir=KOKORO_DIR)
            print(f"  Done: {f}")
        except Exception as e:
            print(f"  Failed: {e}")
            print(f"  Try manually: set HF_ENDPOINT=https://hf-mirror.com")

    for v in KOKORO_VOICES:
        dest = os.path.join(KOKORO_DIR, "voices", f"{v}.pt")
        if os.path.exists(dest):
            print(f"kokoro voice {v} exists, skipping")
            continue
        print(f"Downloading kokoro voice {v}...")
        try:
            hf_hub_download(KOKORO_REPO, f"voices/{v}.pt", local_dir=KOKORO_DIR)
            print(f"  Done: voice {v}")
        except Exception as e:
            print(f"  Failed: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("Downloading Piper Spanish TTS models...")
    print("=" * 50)
    download_piper()

    print("\n" + "=" * 50)
    print("Downloading Kokoro Chinese TTS model...")
    print("=" * 50)
    download_kokoro()

    print("\nAll done. Re-run main.py to start the program.")