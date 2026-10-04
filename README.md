# 会议同传 · Meeting Translator

面向**英文学术会议**的实时同声传译工具：抓取麦克风或系统回环声音，本地做语音识别（ASR），再调用大模型流式翻译成中文，中英对照实时滚动显示，并可导出 Word / PDF / Markdown。

支持物理等专业场景的**术语表**（ASR 提示词 + 译文纠正），会根据电源状态自动切换识别模型与 GPU 功耗。

> **English**: A real-time English→Chinese speech translator for academic meetings on Windows. Local ASR via `faster-whisper`/CTranslate2 on GPU, streaming translation via any OpenAI-compatible LLM API, live bilingual view with glossary support, and export to DOCX/PDF/Markdown. **Ships without PyTorch** — the VAD runs on ONNX Runtime and only ~750 MB of CUDA runtime libraries are bundled, keeping the portable build at ~1.1 GB instead of ~4.6 GB.

---

## 功能特性

- **实时同传**：边说边出中英对照，采集 → 分段 → 识别 → 翻译全程流水线，互不阻塞
- **两种音源**：麦克风（现场会议 / 外放）或系统回环（腾讯会议、Zoom 等线上会议）
- **GPU 加速识别**：基于 `faster-whisper` + CTranslate2，插电用 `distil-whisper-large-v3`，离电自动换 `small.en` + int8
- **流式翻译**：任意 OpenAI 兼容接口（智谱 GLM、硅基流动、DeepSeek…），逐 token 流式回填
- **专业术语表**：`glossary.json` 配置术语对照与译文修正，识别时作为提示词、翻译时按段挑选相关术语，支持热重载
- **会话管理**：历史记录自动落盘、搜索、双击重命名、右键删除
- **一键导出**：Word / PDF / Markdown，支持纯中文、纯英文、左右对照、段段交替四种排版
- **免 Python 分发**：打包后目标机器不装 Python 也能双击运行
- **API Key 加密存储**：Fernet 加密 + 本机机器指纹，换机自动失效而不是明文泄露

---

## 系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（64 位） |
| GPU | NVIDIA 显卡（CUDA 12 + cuDNN 9 运行库**已随包内置**，无需自己装 CUDA） |
| Python | **仅源码运行需要**，3.12；打包版不用装任何东西 |
| 磁盘 | 打包版约 1.1 GB；ASR 模型另需 0.5～1.5 GB |
| 网络 | 翻译需要能访问所选的大模型 API |

> CUDA 运行库（cuBLAS/cuDART）已经打进 `_internal/ctranslate2/`，**目标机器不需要安装 CUDA Toolkit**。

---

## 快速开始

### 方式一：解压使用

1. 解压 `SpeechTranslator-bundle.zip`
2. 把 ASR 模型放到 `E:\models\`（或改设置，见下）
3. 双击 `SpeechTranslator.exe`
4. 点右上角 ⚙ → 「翻译」页填 API Key → 保存
5. 点「▶ 开始翻译」

首次运行前建议先自检，确认环境没有缺件：

```bat
SpeechTranslator.exe --selftest
```

它会把依赖、VAD、CUDA 识别、导出、界面逐个跑一遍，结果同时打印到控制台并写入 exe 同目录的 `selftest_report.txt`（窗口版没有控制台，所以必须落盘）。全部通过返回 0。

### 方式二：源码运行

```bat
git clone <this-repo>
cd meeting_translator

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

---

## 准备 ASR 模型

识别模型**不随包分发**（太大），需要自己下载放到本地目录。项目默认读取 `E:\models`：

```bat
pip install huggingface_hub

hf download Systran/faster-distil-whisper-large-v3 ^
    --local-dir E:\models\faster-distil-whisper-large-v3

hf download Systran/faster-whisper-small.en ^
    --local-dir E:\models\faster-whisper-small.en
```

| 档位 | 模型 | compute_type |
|---|---|---|
| 插电 / 台式机 | `faster-distil-whisper-large-v3` | `float16` |
| 离电 | `faster-whisper-small.en` | `int8_float16` |

模型路径可以直接在 **设置 → 识别 → 插电时模型 / 离电时模型** 里改

---

## 配置说明

点右上角 ⚙ 打开设置，共五页：

| 页 | 内容 |
|---|---|
| **音频** | 音源选择：麦克风 / 系统回环 |
| **识别** | 插电与离电的模型目录、静音阈值（切段灵敏度）、单段最长时长 |
| **翻译** | API 地址、模型名、API Key（密文显示，可临时查看） |
| **显示** | 正文字号（9–24）、英文字体、中文字体 |
| **术语表** | 直接编辑 `glossary.json`，带 JSON 格式化按钮 |

常用翻译服务配置（也可在界面里改）：

```
智谱      https://open.bigmodel.cn/api/paas/v4     GLM-4-Flash-250414
硅基流动  https://api.siliconflow.cn/v1            Qwen/Qwen2.5-7B-Instruct
DeepSeek  https://api.deepseek.com/v1              deepseek-chat
```

也支持环境变量：`SILICONFLOW_API_KEY` / `MT_BASE_URL` / `MT_MODEL`。

### 术语表格式

```json
{
  "version": 1,
  "terms": {
    "Hamiltonian": "哈密顿量",
    "renormalization group": "重整化群"
  },
  "fixups": {
    "哈密顿算子": "哈密顿量",
    "重正化": "重整化"
  }
}
```

- `terms`：术语对照。识别阶段作为 Whisper 提示词；翻译阶段只挑当前段落里真正出现的条目塞进 system prompt，避免一次塞几百条
- `fixups`：译文后处理替换，用来兜住模型偶尔用错的专业词

---

## 打包

```bat
python build.py
```

产物：

| 路径 | 说明 |
|---|---|
| `dist/SpeechTranslator/` | 可直接运行的目录 |
| `release/SpeechTranslator-bundle.zip` | 分发用压缩包（约 685 MB） |

打包要点都在 [`build.spec`](build.spec) 的注释里，主要包括：

- **不含 PyTorch**。VAD 用 ONNX Runtime 直接跑 `assets/silero_vad.onnx`；`ctranslate2.converters`（会 `import torch`）被整条排除
- **自带 CUDA 运行库**。`cublas64_12.dll`、`cublasLt64_12.dll`、`cudart64_12.dll` 会被收集进 `_internal/ctranslate2/`，并由 [`cuda_env.py`](cuda_env.py) 注册搜索目录（源码运行时同一个模块同样生效）
- CUDA DLL 的来源优先是官方 NVIDIA 轮子（`nvidia-cublas-cu12` 等），找不到才回退 `torch\lib`。**缺了会直接报错终止**，而不是产出一个跑不了 GPU 的包

---

## 项目结构

```
main.py               主窗口：UI、状态机、线程编排
audio.py              采集（soundcard）+ Silero VAD 分段（onnxruntime，不依赖 torch）
asr.py                faster-whisper 识别线程（CTranslate2 / CUDA）
mt.py                 流式翻译线程（OpenAI 兼容接口）+ 术语表
export.py             导出 DOCX / PDF / Markdown
session.py            会话数据与本地存储
settings.py           设置读写 + API Key 加密
settings_dialog.py    设置对话框
power.py              电源档位检测、GPU 功率墙、GPU 状态查询
config.py             采样率、块大小、三种电源档位的参数
build.py              一键打包
build.spec            PyInstaller 配置
cuda_env.py           注册 CUDA 运行库搜索路径（源码运行 + 打包运行共用）
assets/               图标、欢迎图、Silero VAD ONNX 权重
glossary.json         术语表
```

### 数据流

```
声卡/麦克风 ──► audio_q ──► VAD 分段 ──► seg_q ──► ASR ──► text_q ──► 翻译
                 (32ms块)   (静音切段)           (GPU)          (流式)
                                                              │
                                            英文立即上屏 ◄────┤
                                            中文占位→回填 ◄────┘
```

`audio_q` 有界（400 块 ≈ 12.8 秒，提供背压）；`seg_q` 有界，但**满了是把最旧的两段合并、而不是丢弃** —— 音频一个采样都不会少，只是那一段会更长、更晚送去识别；`text_q` 不设上限，因为每项只有几十字节，而且英文文本在入队前就已经写进会话了。录音结束时靠 `recording_ref` + 队列空判定各线程自然退出。

> 队列设计的取舍：**「绝不丢内容」和「严格限制内存」不能同时成立**。识别速度长期低于说话速度时，合并会让段越来越长、内存依然会涨（除非把溢出音频写盘暂存）。本项目选择「不丢内容」，并在开始合并时于状态栏提示你识别已经跟不上。

---

## 技术要点：为什么这个项目不需要 PyTorch

之前因为PyTorch，打包出来 `faster-whisper` 项目会连 torch 一起打包（本仓库改版前是 **4.6 GB**，其中 4.08 GB 是 torch）。于是请大肥鱼来这里做了三件事把它降到 **1.1 GB**：

1. **VAD 换 ONNX**。`silero_vad` 这个包在 `import` 的瞬间就会 `import torch`。改成用 `onnxruntime` 直接加载 `assets/silero_vad.onnx`，推理逻辑与官方 `OnnxWrapper` 逐位一致（实测 max diff = 0）。
2. **排除 `ctranslate2.converters`**。`collect_all("ctranslate2")` 会把仅用于**模型转换**的 converters 也当隐藏导入，而它在模块级 `import torch` + `transformers`。运行推理根本用不到。
3. **只带必需的 CUDA 运行库**。这一条最容易踩坑：去掉 torch 之后 GPU 识别会直接报
   `Library cublas64_12.dll is not found or cannot be loaded`
   —— 因为 `cublas64_12.dll` 原本正是由 `torch\lib` 提供的，torch 一被 import 就会把该目录加进 DLL 搜索路径。所以必须把这几个 DLL 单独挑出来随包分发，并在运行时注册搜索目录。

实测结论：真实转写过程中只会加载 `cublas64_12.dll` + `cublasLt64_12.dll`（`cudnn64_9.dll` 仅被探测版本），**Whisper 在 CTranslate2 中不走 cuDNN 算子**，因此那几百 MB 的 `cudnn_*_64_9.dll` 子库全部不需要。

---

## 常见问题

**Q：状态栏一直显示 `GPU: -`？**
`nvidia-smi` 对不支持的字段会返回 `[N/A]`（例如某些 GPU 没有可读的功率墙）。解析失败会连带丢掉温度/功耗/占用率。新版已改为逐字段容错解析，只要有一项有效就会显示。

**Q：改了字号 / 字体没反应？**
这是 Qt 的经典陷阱：**样式表里的字体声明优先级高于 `QWidget.setFont()`**。`STYLE` 里的 `* { font-family }` 和 `QTextEdit { font-size }` 会把设置盖掉。修复方式是往窗口样式表末尾追加 `QTextEdit#EnView` / `#ZhView` 的 ID 选择器规则（ID 优先级更高）。

**Q：功率墙（`nvidia-smi -pl`）不生效？**
设置 GPU 功率墙需要**管理员权限**。没有权限时 `-pl` 会失败，此时程序会自动退避重试（默认 30 秒一次），不会再每 2 秒空跑子进程。

**Q：提示找不到 `silero_vad.onnx`？**
权重在 `assets/silero_vad.onnx`（随包分发）。查找顺序：`exe\assets` → `_internal\assets` → 源码目录。

**Q：打包后设置界面里的上下箭头 / 下拉箭头全都不见了？**
这是 `settings_dialog.py` 特有的坑：它原先用 `Path(__file__).resolve().parent` 定位 `assets/icons`。源码运行没问题，但打包后 `__file__` 指向 PyInstaller 的解包目录 `_internal`，而那里只放了 `silero_vad.onnx`、没有 `icons/` —— QSS 里的 `image: url(...)` 于是指向一个不存在的文件，所有自绘箭头一起消失。（`main.py` 看不出问题，是因为它把 SVG 内联在代码里兜底，用的又是 exe 同目录的 `ASSETS_DIR`。）
现在统一按 `exe\assets` → `_internal\assets` → 源码目录 查找，并且在图标确实找不到时**退化为系统自带箭头**，而不是画不出来。

> 排查思路：只检查「文件存在」是不够的 —— QSS 的 `image: url(*.svg)` 是由 Qt 的 `imageformats/qsvg.dll` 插件加载的，插件缺失时路径再对也画不出来。`--selftest` 里的「设置对话框图标」一项两件事都查。

**Q：识别没反应，界面还停在「录音中」？**
采集 / VAD 线程现在会把异常回传到状态栏。如果设备不可用（没有默认扬声器、回环设备被占用），你会看到 `[错误] 录音线程退出: ...` 而不是静默卡死。

**Q：可以不用 GPU 吗？**
目前识别固定 `device="cuda"`，没有 CPU 回退路径 —— CPU 上跑 large-v3 达不到实时。请确保有可用的 NVIDIA 显卡。

---

## 已知限制

- 仅面向 **英文 → 中文**（识别侧 `language="en"` 硬编码）
- ASR 模型必须外置于本地目录，不随包分发
- `mt.py` 的翻译是单线程串行消费，API 变慢时延迟会累积
- 会话落盘做了节流（最多 1.5 秒写一次），因此程序崩溃时可能丢最后约 1.5 秒的内容；正常关闭/停止都会强制立即落盘
- API Key 的加密只是**防明文**（固定 salt + 机器指纹），并非强安全边界

---

## 许可证

MIT

## 致谢

- 在ONNX的问题始终无法解决的时候，最终我选择请大肥鱼来帮我修好这个问题，顺便完成了这个README。如果没有大肥鱼的帮忙，release版本还得有4.几个GB，即使进行排除，也还有至少2GB。请支持大肥鱼~
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2) —— GPU 语音识别
- [Silero VAD](https://github.com/snakers4/silero-vad) —— 语音活动检测
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) —— 界面
- [soundcard](https://github.com/bastibe/SoundCard) —— 音频采集与系统回环
