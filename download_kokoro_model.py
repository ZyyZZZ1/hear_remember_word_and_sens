"""
下载 Kokoro TTS 中英文语音模型（ONNX）
从 HuggingFace 镜像下载模型和中文语音，构建 NPZ
"""
import os
import urllib.request
import ssl
import numpy as np
import json

MODEL_DIR = os.path.join(os.path.dirname(__file__), "kokoro_models")

HF_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
MIRROR = "https://hf-mirror.com"

MODEL_REMOTE = f"{HF_REPO}/resolve/main/onnx/model.onnx"
MODEL_LOCAL = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")

VOICES_LOCAL = os.path.join(MODEL_DIR, "voices-v1.0.bin")

CHINESE_VOICES = [
    "zf_xiaoxiao", "zf_xiaobei", "zf_xiaoni", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _make_request(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())


def download_file(url, dest, label):
    if os.path.exists(dest) and os.path.getsize(dest) > 100:
        print(f"  {label} 已存在 ({os.path.getsize(dest)/1024/1024:.1f} MB)，跳过")
        return True
    print(f"  下载 {label} ...", end="", flush=True)
    try:
        with _make_request(url) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f" 完成 ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f" 失败: {e}")
        return False


def build_voices_npz(voice_dir, dest_npz):
    if os.path.exists(dest_npz) and os.path.getsize(dest_npz) > 0:
        print(f"  voices.npz 已存在，跳过构建")
        return True
    print("  构建 voices NPZ ...")
    data = {}
    for vname in CHINESE_VOICES:
        src = os.path.join(voice_dir, f"{vname}.bin")
        if os.path.exists(src):
            with open(src, "rb") as f:
                raw = f.read()
            arr = np.frombuffer(raw, dtype=np.float32)
            data[vname] = arr
            print(f"    + {vname}: {arr.shape}")
    if not data:
        print("    未找到任何中文语音文件")
        return False
    import tempfile, shutil
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tf:
        tpath = tf.name
    np.savez_compressed(tpath, **data)
    shutil.copy(tpath, dest_npz)
    os.unlink(tpath)
    print(f"    完成 ({os.path.getsize(dest_npz)/1024/1024:.1f} MB)")
    return True


if __name__ == "__main__":
    os.environ["http_proxy"] = os.environ.get("http_proxy", "http://localhost:3128")
    os.environ["https_proxy"] = os.environ.get("https_proxy", "http://localhost:3128")
    os.makedirs(MODEL_DIR, exist_ok=True)

    print("=== Kokoro 模型下载 ===")

    # 创建 __init__.py（使 kokoro_models 可被 import）
    init_path = os.path.join(MODEL_DIR, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            pass

    # 1. 下载 ONNX 模型 (~300MB)
    model_url = f"{MIRROR}/{MODEL_REMOTE}"
    if not download_file(model_url, MODEL_LOCAL, "kokoro-v1.0.onnx"):
        print(f"\n  模型下载失败，请手动下载：")
        print(f"    {model_url}")
        print(f"  放到 {MODEL_LOCAL}")
        print(f"  或者从 GitHub: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx")
        exit(1)

    # 2. 下载中文语音文件（每个 ~0.5MB）
    print("\n  下载中文语音文件 ...")
    voice_dir = os.path.join(MODEL_DIR, "voices")
    os.makedirs(voice_dir, exist_ok=True)

    voices_ok = 0
    for vname in CHINESE_VOICES:
        voice_url = f"{MIRROR}/{HF_REPO}/resolve/main/voices/{vname}.bin"
        voice_dest = os.path.join(voice_dir, f"{vname}.bin")
        if download_file(voice_url, voice_dest, vname):
            voices_ok += 1

    print(f"  中文语音: {voices_ok}/{len(CHINESE_VOICES)} 下载成功")

    # 3. 下载 tokenizer（用于 Text-to-Phoneme 转写）
    print("\n  下载 tokenizer ...")
    for tf_name in ["tokenizer.json", "tokenizer_config.json", "config.json"]:
        tf_url = f"{MIRROR}/{HF_REPO}/resolve/main/{tf_name}"
        tf_dest = os.path.join(MODEL_DIR, tf_name)
        download_file(tf_url, tf_dest, tf_name)

    # 4. 构建 NPZ
    print("\n  构建合并的声音文件 ...")
    build_voices_npz(voice_dir, VOICES_LOCAL)

    print("\n=== 完成 ===")
    print(f"模型: {MODEL_LOCAL}")
    print(f"声音: {VOICES_LOCAL}")
    print("现在可以运行 main.py 了。")
