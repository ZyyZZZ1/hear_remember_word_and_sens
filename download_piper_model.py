"""
下载 Piper TTS 西班牙语语音模型（全部 4 个）
多个镜像自动重试
"""
import os
import urllib.request
import ssl

MODEL_DIR = os.path.join(os.path.dirname(__file__), "piper_models")

# 所有模型及其 HuggingFace 路径
MODELS = [
    ("es_ES-davefx-medium",     "es/es_ES/davefx/medium"),
    ("es_ES-sharvard-medium",   "es/es_ES/sharvard/medium"),
    ("es_MX-claude-high",       "es/es_MX/claude/high"),
    ("es_AR-daniela-high",      "es/es_AR/daniela/high"),
]

MIRRORS = [
    "https://hf-mirror.com/rhasspy/piper-voices/resolve/main",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main",
]


def download_one(url, dest):
    """下载单个文件，返回 True/False"""
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
        print(f"    完成 ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"    失败: {e}")
        return False


if __name__ == "__main__":
    os.makedirs(MODEL_DIR, exist_ok=True)

    for name, path in MODELS:
        for ext in [".onnx.json", ".onnx"]:
            fn = name + ext
            dest = os.path.join(MODEL_DIR, fn)
            if os.path.exists(dest) and os.path.getsize(dest) > 100:
                print(f"{fn} 已存在 ({os.path.getsize(dest)/1024/1024:.1f} MB)，跳过")
                continue

            print(f"下载 {fn} ...")
            ok = False
            for mirror in MIRRORS:
                url = f"{mirror}/{path}/{fn}"
                print(f"  尝试: {url[:80]}...")
                ok = download_one(url, dest)
                if ok:
                    break

            if not ok:
                print(f"\n  所有镜像均失败！请手动下载 {fn}：")
                print(f"    {MIRRORS[0]}/{path}/{fn}")
                print(f"  放到 {dest}")

    print("\n完成。若所有文件均已下载，重新运行 main.py 即可使用 Piper TTS。")
