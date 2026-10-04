# asr.py
import sys, time, queue, threading, traceback

# 注册 CUDA 运行库搜索路径，必须在 CTranslate2 加载之前执行。
# 去掉 torch 之后 cublas64_12.dll 不再由 torch\lib 提供，不注册就会报
# "Library cublas64_12.dll is not found or cannot be loaded"。
import cuda_env  # noqa: F401

_model_cache = {}
_model_lock  = threading.Lock()

# 显存缓存清理。
#
# 以前这里直接调 torch.cuda.empty_cache()，把 torch 变成了硬依赖。其实它对本
# 程序没有作用：ASR 走 CTranslate2（faster-whisper），显存由 CTranslate2 自己
# 的分配器管理，torch 的 caching allocator 里根本没有这部分张量；VAD 也跑在
# CPU 上。所以打包版（不带 torch）跳过它，显存占用和以前一样。
#
# 这里只在 torch「已经被加载」时才调用它 —— 刻意不写 `import torch`，
# 否则 PyInstaller 的静态分析会顺着这行把 4 GB 的 torch 再塞回包里。
def _release_gpu_cache():
    mod = sys.modules.get("torch")
    if mod is None:
        return
    try:
        mod.cuda.empty_cache()
    except Exception:
        pass


def _get_model(model_path, compute_type, cpu_threads):
    key = (model_path, compute_type, cpu_threads)
    with _model_lock:
        if key not in _model_cache:
            print(f"[ASR] 首次加载模型: {model_path}", flush=True)
            from faster_whisper import WhisperModel
            _model_cache[key] = WhisperModel(
                model_path, device="cuda",
                compute_type=compute_type,
                cpu_threads=cpu_threads, num_workers=1,
            )
        return _model_cache[key]


class ASRWorker(threading.Thread):
    def __init__(self, seg_q, text_q, profile, initial_prompt,
                 stop_event, recording_ref, bridge,
                 on_ready=None, on_error=None):
        super().__init__(daemon=True)
        self.profile        = profile
        self.seg_q          = seg_q
        self.text_q         = text_q
        self.initial_prompt = initial_prompt
        self.stop_event     = stop_event
        self.recording_ref  = recording_ref
        self.bridge         = bridge
        self.on_ready       = on_ready
        self.on_error       = on_error
        self.empty_cache    = profile["empty_cache"]

    def run(self):
        try:
            self._run_impl()
        except Exception as e:
            traceback.print_exc()
            if self.on_error: self.on_error(f"ASR 崩溃: {e}")

    def _run_impl(self):
        try:
            model = _get_model(
                self.profile["asr_model"],
                self.profile["compute_type"],
                self.profile["cpu_threads"],
            )
        except Exception as e:
            traceback.print_exc()
            if self.on_error: self.on_error(f"ASR 加载失败: {e}")
            return

        print(f"[ASR] 就绪: {self.profile['asr_model']}", flush=True)
        if self.on_ready:
            self.on_ready(self.profile["asr_model"])

        n = 0
        while not self.stop_event.is_set():
            try:
                audio = self.seg_q.get(timeout=0.3)
            except queue.Empty:
                if not self.recording_ref[0] and self.seg_q.empty():
                    break
                continue
            try:
                t0 = time.time()
                segments, _ = model.transcribe(
                    audio, language="en",
                    beam_size=1, best_of=1, temperature=0.0,
                    condition_on_previous_text=False,
                    initial_prompt=self.initial_prompt,
                    vad_filter=False,
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    n += 1
                    dt  = time.time() - t0
                    rid = time.time_ns()
                    print(f"[ASR] #{n} ({len(audio)/16000:.2f}s → {dt:.2f}s): {text[:60]}",
                          flush=True)
                    self.bridge.new_en.emit({
                        "rid": rid, "t": time.time(),
                        "en": text, "asr_dt": dt,
                    })
                    self.text_q.put((rid, text, dt))
                if self.empty_cache:
                    _release_gpu_cache()
            except Exception as e:
                traceback.print_exc()
                if self.on_error:
                    self.on_error(f"ASR 运行错误: {e}")

        print("[ASR] 退出", flush=True)