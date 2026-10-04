# build.spec
# -*- mode: python ; coding: utf-8 -*-
"""
打包配置（PyInstaller onedir）。

体积 / 依赖要点
===============
以前 dist/SpeechTranslator 有 4.6 GB，其中 4.08 GB 是 torch + torchaudio。
现在包里完全没有 torch，运行期也不再 import 它。torch 原本是被两处拖进来的：

1. audio.py 里 `from silero_vad import load_silero_vad` —— silero_vad 包在
   import 的时候就 `import torch`（silero_vad/model.py 第 2 行）。
   现在改成用 onnxruntime 直接跑 assets/silero_vad.onnx（见 audio.SileroVAD）。

2. 下面原来用了 `collect_all("ctranslate2")` —— 它会把 ctranslate2 的**所有**
   子模块都当成隐藏导入，包括 ctranslate2.converters.*，而 converters 在模块级
   `import torch`（以及 transformers）。跑推理根本用不到，所以整条过滤掉。

CUDA 运行库（最关键的一步，别删）
--------------------------------
只把 torch 拿掉是不够的：GPU 转写会直接报

    RuntimeError: Library cublas64_12.dll is not found or cannot be loaded

因为 cublas64_12.dll 以前是由 torch\\lib 提供的 —— torch 一旦 import 过，
它的 torch\\lib 就进了 DLL 搜索路径，CTranslate2 顺带就找到了 cuBLAS / cuDNN。
**这正是之前几次「摆脱 torch」失败的真正原因**：不是打包出错，而是运行时
少了 CUDA 运行库。

所以这里把 CTranslate2 真正需要的 CUDA DLL 单独挑出来随包分发到
_internal/ctranslate2/，再由 cuda_env.py 显式注册搜索目录。

到底需要哪几个？实测结论（见下面的 CUDA_DLLS）：
在真实转写过程中枚举进程已加载模块，只有 cublas64_12.dll 和
cublasLt64_12.dll 被真正加载；cudnn64_9.dll 只是被 CTranslate2 探测了一下
版本（它由 ctranslate2 包自带），**cuDNN 那一堆 *_64_9.dll 子库一个都没被加载**
—— Whisper 在 CTranslate2 里不走 cuDNN 算子。

于是那些动辄几百 MB 的 cuDNN 子库全是死重：
    cudnn_engines_precompiled64_9.dll   459 MB
    cudnn_adv64_9.dll                   257 MB
    cudnn_ops64_9.dll                   101 MB
    cudnn_heuristic64_9.dll              56 MB
    cudnn_engines_runtime_compiled64_9.dll  27 MB
    cudnn_cnn64_9.dll / cudnn_graph64_9.dll  5 MB
把它们全部去掉，只留 cuBLAS，实测在
  distil-whisper-large-v3 × float16 × {0.5,1,5,15,29,35,61}s
  distil-whisper-large-v3 × int8_float16 × {2,15,35}s
  faster-whisper-small.en × int8_float16 × {1,8,35}s
  faster-whisper-small.en × float16 × {8}s
共 14 组全部通过（cudart64_12.dll 也没被加载，但只有 0.5 MB，留着当保险）。

DLL 来源
--------
优先用官方 NVIDIA pip 轮子（nvidia-cublas-cu12 等）；找不到就退回 torch\\lib。
也就是说打包机上可以没有 torch，只要有 NVIDIA 轮子即可。
"""
import os
import site
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

SPEC_DIR = Path(SPECPATH if "SPECPATH" in globals() else os.getcwd())

# ------------------------------------------------------------
# CTranslate2 需要的 CUDA 运行库
# ------------------------------------------------------------
CUDA_DLLS = [
    "cublas64_12.dll",      # 必需，108 MB
    "cublasLt64_12.dll",    # 必需，cublas64_12.dll 静态依赖它，643 MB
    "cudart64_12.dll",      # 实测没被加载，但只有 0.5 MB，留着当保险
]
# cudnn64_9.dll 由 ctranslate2 包自带（0.3 MB），不在这里重复收集。


def _cuda_search_dirs():
    """所有可能放着 CUDA DLL 的目录，官方 NVIDIA 轮子优先。"""
    dirs = []
    try:
        site_dirs = list(site.getsitepackages())
    except Exception:
        site_dirs = []
    for sp in site_dirs:
        sp = Path(sp)
        for sub in ("cublas", "cuda_runtime"):     # 官方 NVIDIA pip 轮子
            dirs.append(sp / "nvidia" / sub / "bin")
            dirs.append(sp / "nvidia" / sub / "lib")
        dirs.append(sp / "torch" / "lib")          # 兜底：torch 自带
    cuda_path = os.environ.get("CUDA_PATH")        # 系统装的 CUDA Toolkit
    if cuda_path:
        dirs.append(Path(cuda_path) / "bin")
    return dirs


def _collect_cuda_dlls():
    dirs = _cuda_search_dirs()
    found, missing = [], []
    for name in CUDA_DLLS:
        hit = next((d / name for d in dirs if (d / name).is_file()), None)
        if hit:
            found.append((str(hit), "ctranslate2"))
        else:
            missing.append(name)
    return found, missing


_cuda, _missing = _collect_cuda_dlls()
if _missing:
    raise SystemExit(
        "\n[build.spec] 缺少 CTranslate2 需要的 CUDA 运行库：\n    "
        + "\n    ".join(_missing)
        + "\n\n没有它们，打包出来的 exe 一跑 GPU 转写就会报\n"
          "    Library cublas64_12.dll is not found or cannot be loaded\n"
          "请任选一种方式提供：\n"
          "  pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12\n"
          "  （或者继续留着 torch，从它的 torch\\lib 里取）\n")
binaries += _cuda
print(f"[build.spec] 收集到 {len(_cuda)} 个 CUDA DLL，"
      f"合计 {sum(Path(p).stat().st_size for p, _ in _cuda) / 1024 / 1024:.0f} MB")

# ------------------------------------------------------------
# 三方包
# ------------------------------------------------------------
# PyQt6 交给 PyInstaller 自带的 hook：只收 QtCore/QtGui/QtWidgets/QtSvg
# 以及真正用到的 Qt DLL 和插件（platforms / imageformats / styles）。
# 之前用 collect_all("PyQt6") 会把 Quick3D、Designer、Pdf、Multimedia、
# Qml 等一大堆用不到的 Qt 库一起收进来（约 135 MB）。
hiddenimports += ["PyQt6.QtSvg", "PyQt6.sip"]

for pkg in ("faster_whisper", "soundcard"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# CTranslate2：只收运行期需要的部分，排除 converters（见文件头说明）
d, b, h = collect_all("ctranslate2")
datas += d; binaries += b
hiddenimports += [m for m in h if not m.startswith("ctranslate2.converters")]

# onnxruntime：VAD 的推理后端（PyInstaller 自带 hook，这里兜底声明）
hiddenimports += ["onnxruntime", "onnxruntime.capi._pybind_state"]

# Silero VAD 的 ONNX 权重 + 图标都塞一份进 _internal/assets/。
# 运行时查找顺序统一是：exe\assets → _internal\assets → 源码目录
# （见 audio.vad_model_path / settings_dialog._assets_icons_dir）。
# 图标这份是兜底：万一用户把 exe 同目录的 assets/ 删了或漏拷，
# 设置界面的上下箭头也不会又变没。
datas += [(str(SPEC_DIR / "assets" / "silero_vad.onnx"), "assets")]
_icons_dir = SPEC_DIR / "assets" / "icons"
if _icons_dir.is_dir():
    datas += [(str(p), "assets/icons")
              for p in sorted(_icons_dir.glob("*.svg"))]

# 注意：assets 和 glossary.json 仍然不整体放进 datas，
# 打包后由 build.py 拷到 exe 同目录（用户可自行替换图标等）

# ------------------------------------------------------------
# 分析
# ------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(SPEC_DIR / "cuda_env.py")],
    excludes=[
        # ---- 去掉 torch 全家桶（约 4.08 GB）----
        "torch", "torchaudio", "torchvision", "torchgen",
        "torchcodec", "silero_vad",
        # torch 的传递依赖（跟着 torch 才能进来）
        "sympy", "networkx", "mpmath",
        # ctranslate2 里只在「模型转换」时才用到的部分
        "ctranslate2.converters",
        # ---- 原本就在排除的 ----
        "tkinter", "matplotlib", "scipy", "pandas",
        "IPython", "jupyter", "notebook", "pytest",
        "PyQt5", "PySide2", "PySide6",
        "transformers", "tensorflow", "keras",
        # ---- 用不到的 Qt 模块 ----
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick", "PyQt6.QtWebChannel",
        "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQml",
        "PyQt6.QtQuickWidgets", "PyQt6.QtQuickControls2",
        "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DAnimation",
        "PyQt6.QtDesigner", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning",
        "PyQt6.QtSerialPort", "PyQt6.QtSql", "PyQt6.QtTest",
        "PyQt6.QtWebSockets", "PyQt6.QtCharts", "PyQt6.QtDataVisualization",
    ],
    noarchive=False,
)

# ------------------------------------------------------------
# 去掉 CUDA DLL 的重复副本
# ------------------------------------------------------------
# PyInstaller 会顺着 cublas64_12.dll 的导入表把 cublasLt64_12.dll 再收一份，
# 并且按源路径的包结构放进 _internal/torch/lib/ —— 既白白多占 643 MB，
# 又会在包里凭空多出一个 torch 目录（自检会误判成 torch 没删干净）。
# 这里把这些 CUDA DLL 只保留 ctranslate2/ 下的那一份。
_cuda_names = {n.lower() for n in CUDA_DLLS} | {"cudnn64_9.dll"}
_kept, _dropped = [], []
for _entry in a.binaries:
    _dest = str(_entry[0]).replace("\\", "/")
    _names = {os.path.basename(str(x)).lower() for x in _entry[:2]}
    if (_names & _cuda_names) and not _dest.startswith("ctranslate2/"):
        _dropped.append(_dest)
        continue
    _kept.append(_entry)
a.binaries = _kept
if _dropped:
    print(f"[build.spec] 去重 CUDA DLL，移除 {len(_dropped)} 个重复副本："
          f" {', '.join(sorted(set(_dropped)))}")

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SpeechTranslator",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SpeechTranslator",
    contents_directory="_internal",   # 依赖都收进 _internal/ 子目录
)
