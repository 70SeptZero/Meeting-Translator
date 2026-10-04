# cuda_env.py
# -*- coding: utf-8 -*-
"""
注册 CTranslate2 需要的 CUDA 运行库（cuBLAS / cuDART）搜索路径。

背景（这是去掉 torch 路上最容易踩的坑）
---------------------------------------
torch 一旦被 import，就会把自带的 torch\\lib 加进 DLL 搜索路径，
CTranslate2 顺带就从那里找到了 cublas64_12.dll。所以把 torch 拿掉之后，
GPU 转写会直接报：

    RuntimeError: Library cublas64_12.dll is not found or cannot be loaded

看起来像打包出错，其实是运行时少了 CUDA 运行库。

这个模块把「找到 CUDA DLL 并注册搜索目录」集中到一处，两种运行方式共用：

  * 打包运行：build.spec 把它当 runtime hook 执行，目录是 _internal\\ctranslate2
    （DLL 由 build.spec 收集进包）
  * 源码运行：import 本模块即生效，从已安装的轮子里找 —— 优先官方
    nvidia-*-cu12 轮子，其次 torch\\lib，最后系统 CUDA Toolkit

两个必须注意的 Windows 细节
--------------------------
1) os.add_dll_directory 返回的 cookie 必须一直存活，否则目录会被立刻移除
   —— 所以挂在 sys 上，保证整个进程生命周期内不释放；
2) AddDllDirectory 注册的目录，只有在 SetDefaultDllDirectories 打开了
   LOAD_LIBRARY_SEARCH_DEFAULT_DIRS 之后才真正参与搜索，
   否则 LoadLibrary 依旧返回 126（找不到模块），照样加载失败。
"""
import ctypes
import os
import sys

_COOKIE_KEY = "_mt_cuda_dll_cookies"
_FLAG_KEY = "_mt_cuda_dll_registered"
_CUBLAS = "cublas64_12.dll"


def _candidate_dirs():
    dirs = []

    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            dirs.append(os.path.join(base, "ctranslate2"))
            dirs.append(base)
        dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
        return dirs

    # 源码运行：从已安装的轮子里找
    try:
        import site
        site_dirs = list(site.getsitepackages())
    except Exception:
        site_dirs = []
    for sp in site_dirs:
        for sub in ("cublas", "cuda_runtime"):
            dirs.append(os.path.join(sp, "nvidia", sub, "bin"))
            dirs.append(os.path.join(sp, "nvidia", sub, "lib"))
        dirs.append(os.path.join(sp, "torch", "lib"))
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        dirs.append(os.path.join(cuda_path, "bin"))
    return dirs


def register():
    """幂等注册。返回本次实际新注册的目录列表。

    幂等标记放在 sys 上而不是模块全局变量，这样即使本文件既被当成
    PyInstaller runtime hook 执行、又被应用 import 成模块（两个模块对象），
    也只会注册一次。
    """
    if sys.__dict__.get(_FLAG_KEY):
        return []
    sys.__dict__[_FLAG_KEY] = True

    if sys.platform != "win32":
        return []

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetDefaultDllDirectories.argtypes = [ctypes.c_uint]
        # LOAD_LIBRARY_SEARCH_DEFAULT_DIRS = 应用目录 + System32 + 用户目录
        k32.SetDefaultDllDirectories(0x00001000)
    except Exception:
        pass

    cookies = sys.__dict__.setdefault(_COOKIE_KEY, [])
    added = []
    for d in _candidate_dirs():
        if d in added or not os.path.isdir(d):
            continue
        try:
            cookies.append(os.add_dll_directory(d))
            added.append(d)
        except Exception:
            pass

    if not any(os.path.isfile(os.path.join(d, _CUBLAS)) for d in added):
        print("[CUDA] 没找到 cuBLAS 运行库，GPU 识别会失败。请任选一种：\n"
              "       pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12\n"
              "       （或者保留 torch 安装，从它的 torch\\lib 里取）",
              flush=True)
    return added


# 模块被 import（源码运行）或被 runtime hook exec（打包运行）时立即生效
register()
