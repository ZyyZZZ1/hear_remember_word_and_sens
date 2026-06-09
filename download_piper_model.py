"""
下载 Piper TTS 西班牙语语音模型
来源：HuggingFace rhasspy/piper-voices
"""
import os
import urllib.request

MODEL_DIR = os.path.join(os.path.dirname(__file__), "piper_models")
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low"
FILES = [
    "es_ES-carlfm-x_low.onnx",
    "es_ES-carlfm-x_low.onnx.json",
]

# 如果 HuggingFace 连不上，改用镜像：
MIRROR_URL = "https://hf-mirror.com/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low"


def download(url_base, filename):
    url = f"{url_base}/{filename}"
    dest = os.path.join(MODEL_DIR, filename)
    print(f"下载 {filename} ...")
    try:
        urllib.request.urlretrieve(url, dest)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"  完成 ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  失败: {e}")


if __name__ == "__main__":
    os.makedirs(MODEL_DIR, exist_ok=True)

    for fn in FILES:
        dest = os.path.join(MODEL_DIR, fn)
        if os.path.exists(dest):
            print(f"{fn} 已存在，跳过")
            continue
        # 先试主站
        try:
            download(BASE_URL, fn)
        except Exception:
            # 再试镜像
            print(f"  主站失败，尝试镜像...")
            try:
                download(MIRROR_URL, fn)
            except Exception as e:
                print(f"  镜像也失败: {e}")
                print(f"  请手动下载到 {dest}")
                print(f"  URL: {BASE_URL}/{fn}")

    print("\n下载完成。重新运行 main.py 即可使用 Piper TTS。")
