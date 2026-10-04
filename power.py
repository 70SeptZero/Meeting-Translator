# power.py
import subprocess, sys, threading, time
import psutil

# Windows：创建子进程时不弹控制台
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    _NO_WINDOW = 0


class PowerManager:
    # 设置功率墙失败后，隔多久才允许再试（秒）。见 set_power_limit 说明。
    PL_RETRY_INTERVAL = 30.0

    def __init__(self):
        self._battery = psutil.sensors_battery()
        self._is_laptop = self._battery is not None
        self._last_pl = None
        self._pl_fail_ts = 0.0
        self._gpu_cache = None
        self._gpu_cache_ts = 0.0
        self._gpu_lock = threading.Lock()

    @property
    def is_laptop(self):
        return self._is_laptop

    def on_battery(self) -> bool:
        if not self._is_laptop:
            return False
        b = psutil.sensors_battery()
        return b is not None and not b.power_plugged

    def profile_name(self) -> str:
        if not self._is_laptop:
            return "desktop"
        return "battery" if self.on_battery() else "ac"

    def set_power_limit(self, watts):
        """设置功率墙：相同值不重复调用，失败后退避重试。

        为什么要退避：nvidia-smi 单次要 60~80ms，而这个方法是被 GUI 的
        2 秒定时器调用的。没有管理员权限时 `-pm 1` / `-pl` 都会失败；
        老代码不记录失败，于是每 2 秒白跑两次子进程，界面跟着一顿。
        """
        if watts is None:
            return False
        if self._last_pl == watts:
            return True

        now = time.time()
        if now - self._pl_fail_ts < self.PL_RETRY_INTERVAL:
            return False

        try:
            subprocess.run(
                ["nvidia-smi", "-pm", "1"],
                check=False, capture_output=True, timeout=3,
                creationflags=_NO_WINDOW,
            )
            subprocess.run(
                ["nvidia-smi", "-pl", str(watts)],
                check=True, capture_output=True, timeout=3,
                creationflags=_NO_WINDOW,
            )
            self._last_pl = watts
            self._pl_fail_ts = 0.0
            return True
        except Exception:
            self._pl_fail_ts = now
            return False

    def gpu_info(self, max_age: float = 1.5):
        """带缓存的 GPU 查询，max_age 秒内返回缓存。

        nvidia-smi 对「不支持的字段」会返回 [N/A]（很常见，比如某些 GPU
        没有可读的功率墙）。老代码直接 float("[N/A]") 会抛异常，被
        bare except 吞掉后 return None —— 结果整个 GPU 信息都取不到，
        状态栏永远显示「GPU: -」。所以这里改成逐个字段容错解析，
        数值字段解不出来就置 None，只要还有有效字段就照常返回。

        另外 timeout 从 1s 放宽到 3s：这个方法现在跑在后台线程上，
        不再阻塞界面，没必要卡那么紧；多卡时也只取第一行。
        """
        with self._gpu_lock:
            now = time.time()
            if self._gpu_cache and (now - self._gpu_cache_ts) < max_age:
                return self._gpu_cache
            try:
                out = subprocess.check_output(
                    ["nvidia-smi",
                     "--query-gpu=temperature.gpu,power.draw,power.limit,utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    timeout=3, text=True,
                    creationflags=_NO_WINDOW,
                )
            except Exception:
                return None

            first = next((ln for ln in out.strip().splitlines() if ln.strip()), "")
            parts = [x.strip() for x in first.split(",")]

            def _num(idx, cast):
                try:
                    return cast(parts[idx])
                except Exception:
                    return None

            info = {
                "temp":        _num(0, int),
                "power":       _num(1, float),
                "power_limit": _num(2, float),
                "util":        _num(3, int),
            }
            if all(v is None for v in info.values()):
                return None
            self._gpu_cache = info
            self._gpu_cache_ts = now
            return info