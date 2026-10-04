# config.py
MODELS_DIR = r"E:\models"

# ============================================================
# 电源档位
# ============================================================
PROFILES = {
    "ac": {                              # 插电
        "asr_model":    rf"{MODELS_DIR}\faster-distil-whisper-large-v3",
        "compute_type":  "float16",
        "cpu_threads":   4,
        "gpu_power_w":   100,            # 插电可放 100W
        "empty_cache":   True,
    },
    "battery": {                         # 离电
        "asr_model":    rf"{MODELS_DIR}\faster-whisper-small.en",   # 换更小的英文模型
        "compute_type":  "int8_float16",
        "cpu_threads":   2,
        "gpu_power_w":   40,             # 功率墙压到 40W
        "empty_cache":   False,
    },
    "desktop": {                         # 台式机，不限制
        "asr_model":    rf"{MODELS_DIR}\faster-distil-whisper-large-v3",
        "compute_type":  "float16",
        "cpu_threads":   6,
        "gpu_power_w":   None,
        "empty_cache":   True,
    },
}

SR = 16000
BLOCK_MS = 32
BLOCK = SR * BLOCK_MS // 1000
PREROLL_MS = 300
MIN_SPEECH_MS = 350
