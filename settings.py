# settings.py
import json, hashlib, base64, platform, uuid
from pathlib import Path

from config import MODELS_DIR

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


# ============================================================
# 设备指纹
# ============================================================
def _get_machine_id() -> str:
    system = platform.system()
    if system == "Windows":
        try:
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            winreg.CloseKey(k)
            return val
        except Exception:
            pass
    elif system == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
            for line in out.decode().splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=")[1].strip().strip('"')
        except Exception:
            pass
    elif system == "Linux":
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                return Path(p).read_text().strip()
            except Exception:
                continue
    return f"{uuid.getnode():x}"      # 兜底：MAC 地址


def _derive_key(machine_id: str) -> bytes:
    salt = b"meeting-translator-v1"     # 固定 salt，可自定义
    h = hashlib.pbkdf2_hmac("sha256", machine_id.encode(), salt, 100_000)
    return base64.urlsafe_b64encode(h[:32])


class _Crypto:
    def __init__(self):
        self.ok = _HAS_CRYPTO
        if self.ok:
            self.f = Fernet(_derive_key(_get_machine_id()))

    def encrypt(self, s: str) -> str:
        if not s or not self.ok: return s
        return self.f.encrypt(s.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token or not self.ok: return token
        return self.f.decrypt(token.encode()).decode()


# ============================================================
# 设置
# ============================================================
DEFAULT = {
    "audio_source":      "mic",
    # 模型路径只在 config.MODELS_DIR 定义一次，避免两处硬编码各自漂移
    "asr_model":         rf"{MODELS_DIR}\faster-distil-whisper-large-v3",
    "asr_model_battery": rf"{MODELS_DIR}\faster-whisper-small.en",
    "mt_base_url":       "https://open.bigmodel.cn/api/paas/v4",
    "mt_model":          "GLM-4-Flash-250414",
    "mt_api_key":        "",
    "font_size":         14,
    "en_font":           "Times New Roman",
    "zh_font":           "Microsoft YaHei",
    "silence_ms":        600,
    "max_seg_s":         20,
}

SENSITIVE_KEYS = {"mt_api_key"}


class Settings:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = dict(DEFAULT)
        self.crypto = _Crypto()
        self.load()

    def load(self):
        if not self.path.exists(): return
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Settings] 读取失败: {e}")
            return

        # 解密敏感字段
        for k in SENSITIVE_KEYS:
            v = saved.get(k, "")
            if isinstance(v, str) and v.startswith("enc:"):
                try:
                    saved[k] = self.crypto.decrypt(v[4:])
                except Exception:
                    # 换设备 / 文件损坏 / 未装 cryptography
                    print(f"[Settings] {k} 解密失败，已清空", flush=True)
                    saved[k] = ""
        self.data.update(saved)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        out = dict(self.data)
        # 加密敏感字段
        for k in SENSITIVE_KEYS:
            v = out.get(k, "")
            if v and self.crypto.ok:
                out[k] = "enc:" + self.crypto.encrypt(v)
        self.path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def get(self, key, default=None):
        return self.data.get(key, DEFAULT.get(key, default))

    def set(self, key, value):
        self.data[key] = value