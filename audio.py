# audio.py
import collections, queue, sys, threading
from pathlib import Path
import numpy as np
from config import SR, BLOCK, PREROLL_MS, MIN_SPEECH_MS

VAD_MODEL_NAME = "silero_vad.onnx"


def _log(msg):
    print(f"[Audio] {msg}", flush=True)


# ============================================================
# Silero VAD（ONNX 版，不依赖 torch）
# ------------------------------------------------------------
# 以前用 silero_vad.load_silero_vad()，那个包在 import 时就会
# import torch，于是 PyInstaller 被迫把 4 GB 的 torch 打进包里。
# 这里直接用 onnxruntime 跑官方的 silero_vad.onnx 权重，
# 网络结构与推理逻辑和官方 OnnxWrapper 保持一致（CPU、单线程）。
# ============================================================
def vad_model_path() -> Path:
    """按优先级找 VAD 权重：exe 同目录 → _internal → 源码目录 → venv"""
    here = Path(__file__).resolve().parent
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        cands.append(exe_dir / "assets" / VAD_MODEL_NAME)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cands.append(Path(meipass) / "assets" / VAD_MODEL_NAME)
    cands.append(here / "assets" / VAD_MODEL_NAME)
    # 开发环境兜底：直接从已安装的 silero_vad 包里取（只做文件检查，不 import）
    cands.append(Path(sys.prefix) / "Lib" / "site-packages" /
                 "silero_vad" / "data" / VAD_MODEL_NAME)
    for p in cands:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"找不到 {VAD_MODEL_NAME}，已查找：\n  " +
        "\n  ".join(str(c) for c in cands))


class SileroVAD:
    """silero-vad 的 ONNX 推理封装（等价于官方 OnnxWrapper，但不依赖 torch）。"""

    def __init__(self, model_path, force_onnx_cpu=True):
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        path = str(model_path)
        if force_onnx_cpu and "CPUExecutionProvider" in \
                onnxruntime.get_available_providers():
            self.session = onnxruntime.InferenceSession(
                path, providers=["CPUExecutionProvider"], sess_options=opts)
        else:
            self.session = onnxruntime.InferenceSession(path, sess_options=opts)

        # 带 "16k" 的模型只支持 16 kHz；silero_vad.onnx 同时支持 8k/16k
        self.sample_rates = [16000] if "16k" in path else [8000, 16000]
        self.reset_states()

    # ---------- 内部状态 ----------
    def reset_states(self, batch_size=1):
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.zeros(0, dtype=np.float32)
        self._last_sr = 0
        self._last_batch_size = 0

    def _validate_input(self, x, sr: int):
        if x.ndim == 1:
            x = x[None, :]
        if x.ndim > 2:
            raise ValueError(f"Too many dimensions for input audio chunk {x.ndim}")

        if sr != 16000 and (sr % 16000 == 0):
            step = sr // 16000
            x = x[:, ::step]
            sr = 16000

        if sr not in self.sample_rates:
            raise ValueError(
                f"Supported sampling rates: {self.sample_rates} (or multiply of 16000)")
        if sr / x.shape[1] > 31.25:
            raise ValueError("Input audio chunk is too short")

        return x, sr

    # ---------- 推理 ----------
    def __call__(self, x, sr: int):
        x = np.asarray(x, dtype=np.float32)
        x, sr = self._validate_input(x, sr)

        num_samples = 512 if sr == 16000 else 256
        if x.shape[-1] != num_samples:
            raise ValueError(
                f"Provided number of samples is {x.shape[-1]} "
                f"(Supported values: 256 for 8000 sample rate, 512 for 16000)")

        batch_size = x.shape[0]
        context_size = 64 if sr == 16000 else 32

        if not self._last_batch_size:
            self.reset_states(batch_size)
        if self._last_sr and self._last_sr != sr:
            self.reset_states(batch_size)
        if self._last_batch_size and self._last_batch_size != batch_size:
            self.reset_states(batch_size)

        if not len(self._context):
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)

        x = np.concatenate([self._context, x], axis=1)

        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr":    np.array(sr, dtype="int64"),
        }
        out, state = self.session.run(None, ort_inputs)

        self._state = state
        self._context = x[..., -context_size:]
        self._last_sr = sr
        self._last_batch_size = batch_size

        return out.squeeze()


# ============================================================
# 采集
# ============================================================
def capture_loopback(out_q, stop_event, recording_ref, level_ref=None):
    import soundcard as sc
    spk = sc.default_speaker()
    _log(f"扬声器: {spk.name}")
    mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
    _log(f"回环设备: {mic.name}")
    with mic.recorder(samplerate=SR, channels=1, blocksize=BLOCK) as rec:
        while not stop_event.is_set() and recording_ref[0]:
            data = rec.record(numframes=BLOCK)[:, 0].astype(np.float32)
            out_q.put(data)
            if level_ref is not None:
                level_ref[0] = float(np.sqrt(np.mean(data.astype(np.float64)**2)))


def capture_mic(out_q, stop_event, recording_ref, level_ref=None):
    import soundcard as sc
    mic = sc.default_microphone()
    _log(f"麦克风: {mic.name}")
    with mic.recorder(samplerate=SR, channels=1, blocksize=BLOCK) as rec:
        while not stop_event.is_set() and recording_ref[0]:
            data = rec.record(numframes=BLOCK)[:, 0].astype(np.float32)
            out_q.put(data)
            if level_ref is not None:
                level_ref[0] = float(np.sqrt(np.mean(data.astype(np.float64)**2)))


# ============================================================
# 分段队列
# ============================================================
class SegmentQueue:
    """有上限的语音段队列 —— 满了不丢弃，而是把最旧的两段合并。

    为什么要这么设计
    ----------------
    这个队列的源头是**实时音频**：一旦在这里丢东西，转写内容就永久缺失，
    事后补不回来。所以上限不能靠「丢掉最旧的一段」来实现。

    合并策略：超过上限时，把**最旧的两段**（它们在时间上相邻，拼起来就是
    一段更长的连续语音）合并成一段并放回队首。这样音频一个采样都不少，
    顺序也不会乱，代价只是那一段变得更长、更晚送去识别。
    接口对齐 queue.Queue（put / get / get_nowait / empty），
    线程之间用 Condition 同步。

    说清楚代价：如果识别速度长期低于说话速度，合并会让段越来越长，
    内存依然会涨。这是物理限制，任何队列设计都躲不掉 ——
    「绝不丢内容」和「严格限制内存」不能同时成立，除非把溢出的音频
    写到磁盘暂存。只要不是长期过载，合并只是偶尔发生，内容完整。
    """

    def __init__(self, maxlen=48, on_merge=None):
        self._items = collections.deque()
        self._maxlen = maxlen
        self._cond = threading.Condition()
        self._on_merge = on_merge
        self.merged = 0                     # 累计合并次数，供 UI 提示用

    def put(self, seg):
        with self._cond:
            self._items.append(seg)
            # 超上限就合并最旧的两段。必须从队首取、合并后放回队首 ——
            # 曾经写成「最旧段 + 新段」再 append 到队尾，结果音频顺序全乱了
            # （采样数没变，但拼出来的整段话是错位的）。
            if len(self._items) > self._maxlen:
                merged = np.concatenate([self._items.popleft(),
                                         self._items.popleft()])
                self._items.appendleft(merged)
                self.merged += 1
                if self._on_merge is not None:
                    try:
                        self._on_merge(self.merged)
                    except Exception:
                        pass
            self._cond.notify()

    def get(self, timeout=None):
        with self._cond:
            if not self._items:
                self._cond.wait(timeout)
            if self._items:
                return self._items.popleft()
            raise queue.Empty

    def get_nowait(self):
        with self._cond:
            if not self._items:
                raise queue.Empty
            return self._items.popleft()

    def empty(self):
        with self._cond:
            return not self._items

    def qsize(self):
        with self._cond:
            return len(self._items)


# ============================================================
# 分段
# ============================================================
class Segmenter:
    def __init__(self, silence_ms, max_seg_s):
        self.vad = SileroVAD(vad_model_path())
        self.preroll_n    = int(PREROLL_MS / 1000 * SR)
        self.silence_n    = int(silence_ms / 1000 * SR)
        self.min_speech_n = int(MIN_SPEECH_MS / 1000 * SR)
        self.max_n        = int(max_seg_s * SR)
        self.preroll, self.seg = np.zeros(0, np.float32), []
        self.seg_len, self.silence, self.in_speech = 0, 0, False

    def feed(self, chunk):
        prob = float(self.vad(chunk, SR))
        speech = prob > 0.5
        if not self.in_speech:
            self.preroll = np.concatenate([self.preroll, chunk])[-self.preroll_n:]
            if speech:
                self.in_speech, self.seg = True, [self.preroll]
                self.seg_len, self.silence = len(self.preroll), 0
                self.preroll = np.zeros(0, np.float32)
            return None
        self.seg.append(chunk)
        self.seg_len += len(chunk)
        self.silence = 0 if speech else self.silence + len(chunk)
        if self.silence >= self.silence_n or self.seg_len >= self.max_n:
            audio = np.concatenate(self.seg)
            if self.silence:
                audio = audio[:-self.silence]
            self.in_speech, self.seg = False, []
            self.seg_len, self.silence = 0, 0
            self.vad.reset_states()
            if len(audio) >= self.min_speech_n:
                return audio
        return None


def vad_loop(audio_q, seg_q, profile, stop_event, recording_ref):
    seg = Segmenter(profile["silence_ms"], profile["max_seg_s"])
    n = 0
    while not stop_event.is_set():
        try:
            chunk = audio_q.get(timeout=0.2)
        except queue.Empty:
            if not recording_ref[0] and audio_q.empty():
                break
            continue
        s = seg.feed(chunk)
        if s is not None:
            n += 1
            print(f"[VAD] 语音段 #{n}: {len(s)/SR:.2f}s", flush=True)
            seg_q.put(s)
    print("[VAD] 退出", flush=True)
