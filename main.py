# main.py
"""
会议同传 · 主界面

【UI 定制】
- 样式 QSS：STYLE
- 图标 SVG：SVG
- 布局：_build_sidebar / _build_topbar / _build_welcome /
         _build_content / _build_bottom_bar
"""
import os
import sys

# 模型全部走本地目录，禁掉 huggingface 的联网检查，避免加载时卡在网络超时
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import queue
import threading
import time
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="data discontinuity in recording")

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QPoint, QSize
from PyQt6.QtGui import (QTextCursor, QFont, QIcon, QPixmap,
                         QPainter, QAction)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QListWidget,
    QListWidgetItem, QTextEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QFileDialog, QMessageBox, QCheckBox, QLineEdit,
    QToolButton, QFrame, QStackedWidget, QMenu, QStatusBar,
)

from config import PROFILES
from power import PowerManager
from audio import capture_loopback, capture_mic, vad_loop, SegmentQueue
from asr import ASRWorker
from mt import Translator, load_glossary, mt_loop
from export import MODES, EXPORTERS
from session import SessionStore
from settings import Settings
from settings_dialog import SettingsDialog

# 数据目录：始终放在 exe 同目录（可读写）
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent

GLOSSARY_PATH = _APP_DIR / "glossary.json"
DATA_DIR      = _APP_DIR / "data" / "sessions"
SETTINGS_PATH = _APP_DIR / "data" / "settings.json"
ASSETS_DIR    = _APP_DIR / "assets"


# ============================================================
# SVG 图标
# ============================================================
SVG = {
    "expand":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="3" y="4" width="18" height="16" rx="2.5"/>'
                '<line x1="9" y1="4" x2="9" y2="20"/></svg>',

    "new":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M12 5v14M5 12h14"/></svg>',

    "collapse": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M15 18 9 12l6-6"/></svg>',

    "zh":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                '<line x1="9" y1="4" x2="9" y2="20"/>'
                '<line x1="12" y1="10" x2="18" y2="10"/>'
                '<line x1="12" y1="14" x2="16" y2="14"/></svg>',

    "en":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                '<line x1="15" y1="4" x2="15" y2="20"/>'
                '<line x1="6" y1="10" x2="12" y2="10"/>'
                '<line x1="6" y1="14" x2="10" y2="14"/></svg>',

    "both":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                '<line x1="12" y1="4" x2="12" y2="20"/></svg>',

    "reload":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M19.64 14.7a8.1 8.1 0 1 1-1.91-8.42L21.9 10.2"/>'
                '<polyline points="21.9 4.8 21.9 10.2 16.5 10.2"/></svg>',

    "export":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M12 3.5v12"/>'
                '<path d="m7 10.5 5 5 5-5"/>'
                '<path d="M5 20h14"/></svg>',

    "mic":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="9" y="2" width="6" height="12" rx="3"/>'
                '<path d="M5 11v1a7 7 0 0 0 14 0v-1"/>'
                '<path d="M12 19v3"/></svg>',

    "stop":     '<svg viewBox="0 0 24 24" fill="currentColor">'
                '<rect x="7" y="7" width="10" height="10" rx="2.5"/></svg>',

    "settings": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<circle cx="12" cy="12" r="3"/>'
                '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 '
                '2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 '
                '2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 '
                '2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 '
                '0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 '
                '0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 '
                '1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 '
                '0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 '
                '2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 '
                '1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',

    "logo":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<circle cx="12" cy="12" r="9"/>'
                '<path d="M8.2 15.2c1.7-1 2.8-2.6 2.8-4.5"/>'
                '<path d="M15.8 8.8c-1.7 1-2.8 2.6-2.8 4.5"/>'
                '<circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>',
}

def _clean_font_name(name, fallback=""):
    """清掉会破坏 QSS 的字符 —— 字体名来自可编辑下拉框，属于用户输入"""
    name = (name or "").strip()
    for ch in ('"', "'", "{", "}", ";", "\\", "\n", "\r"):
        name = name.replace(ch, "")
    return name.strip() or fallback


def _resource_path(rel: str) -> Path:
    """
    资源查找顺序：
    1. 打包运行时：exe 同目录（assets/glossary.json 放外面）
    2. 打包运行时：_internal 目录（兜底）
    3. 源码运行：脚本同目录
    """
    if getattr(sys, "frozen", False):
        # 优先 exe 同目录
        exe_dir = Path(sys.executable).parent
        p = exe_dir / rel
        if p.exists():
            return p
        # 兜底：PyInstaller 的 _internal
        return Path(sys._MEIPASS) / rel
    return Path(__file__).parent / rel

def svg_icon(name, size=20, color="#4b5563"):
    """
    优先从 assets/icons/{name}.svg 加载，找不到则用内置 SVG 兜底。

    注意：旧代码找的是 assets/icon/（单数），而实际目录叫 assets/icons/，
    所以自定义图标永远加载不到、一直静默走内置兜底。这里两个都找，
    并保留 assets/icon/ 作为兼容。
    """
    custom = next((p for p in (ASSETS_DIR / "icons" / f"{name}.svg",
                               ASSETS_DIR / "icon" / f"{name}.svg")
                   if p.exists()), None)
    if custom is not None:
        try:
            svg = custom.read_text(encoding="utf-8")
        except Exception:
            svg = SVG.get(name, SVG["logo"])
    else:
        svg = SVG.get(name, SVG["logo"])

    # 2. 替换颜色占位符
    svg = svg.replace("currentColor", color)

    # 3. 渲染
    r = QSvgRenderer(svg.encode("utf-8"))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p)
    p.end()
    return QIcon(pix)


def icon_button(name, tooltip="", size=32, icon_size=18, color="#4b5563"):
    btn = QToolButton()
    btn.setIcon(svg_icon(name, icon_size, color))
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setObjectName("IconBtn")
    return btn


# ============================================================
# QSS
# ============================================================
STYLE = """
* { font-family: 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif; }
QMainWindow { background: #ffffff; }

QFrame#SideBar { background: #f9fafb; border-right: 1px solid #ececec; }
QFrame#TopBar  { background: #ffffff; border-bottom: 1px solid #ececec; }
QWidget#RightArea { background: #ffffff; }

QToolButton#IconBtn { border: none; border-radius: 8px; background: transparent; }
QToolButton#IconBtn:hover { background: #f3f4f6; }
QToolButton#IconBtn:pressed { background: #e5e7eb; }

QLineEdit {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 6px 10px; font-size: 13px; color: #1f2937;
}
QLineEdit:focus { border-color: #93c5fd; }
QLineEdit#TitleEdit {
    background: transparent; border: none;
    font-size: 15px; font-weight: 600; color: #111827; padding: 2px 6px;
}
QLineEdit#TitleEdit:focus { background: #f3f4f6; border-radius: 6px; }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item {
    padding: 10px 12px; border-radius: 8px;
    color: #374151; margin: 2px 4px; font-size: 13px;
}
QListWidget::item:hover    { background: #eef2f7; }
QListWidget::item:selected { background: #dbeafe; color: #1e40af; }

QTextEdit {
    background: transparent; border: none;
    padding: 16px 20px; font-size: 14px; color: #1f2937;
    selection-background-color: #bfdbfe;
}

QPushButton#WelcomeBtn {
    background: #2563eb; color: white; border: 1px solid transparent;
    border-radius: 20px; padding: 12px 48px;
    font-size: 15px; font-weight: 600;
    min-height: 35px;
}
QPushButton#WelcomeBtn:hover { background: #1d4ed8; }

QPushButton#MicBtn, QPushButton#StopRecBtn {
    border: none; border-radius: 26px; padding: 0;
}
QPushButton#MicBtn        { background: #2563eb; }
QPushButton#MicBtn:hover  { background: #1d4ed8; }
QPushButton#StopRecBtn      { background: #dc2626; }
QPushButton#StopRecBtn:hover { background: #b91c1c; }

/* 停止翻译：红色圆角矩形 + 文字 */
QPushButton#StopMtBtn {
    background: #dc2626; color: #ffffff;
    border: none; border-radius: 10px; padding: 0 20px;
    font-size: 14px; font-weight: 600;
    min-width: 120px;
}
QPushButton#StopMtBtn:hover { background: #b91c1c; }

/* 状态栏左侧常驻状态文字 */
QLabel#InfoLbl { color: #4b5563; font-size: 12px; padding-left: 6px; }

QStatusBar {
    background: #f9fafb; border-top: 1px solid #ececec;
    color: #6b7280; font-size: 12px;
}
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical {
    background: #d1d5db; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #9ca3af; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QMenu { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 8px 24px; border-radius: 6px; font-size: 13px; }
QMenu::item:selected { background: #eff6ff; color: #1e40af; }
"""


# ============================================================
# 可双击编辑标题
# ============================================================
class EditableTitle(QLineEdit):
    editing_done = pyqtSignal(str)

    def __init__(self, text=""):
        super().__init__(text)
        self.setObjectName("TitleEdit")
        self.setReadOnly(True)
        self.editingFinished.connect(self._on_done)

    def mouseDoubleClickEvent(self, e):
        if self.isReadOnly():
            self.setReadOnly(False)
            self.selectAll()
            self.setFocus()
        else:
            super().mouseDoubleClickEvent(e)

    def _on_done(self):
        if not self.isReadOnly():
            self.setReadOnly(True)
            self.editing_done.emit(self.text())

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_done(); self.clearFocus(); return
        if e.key() == Qt.Key.Key_Escape:
            self.setReadOnly(True); self.clearFocus(); return
        super().keyPressEvent(e)


# ============================================================
# 信号桥
# ============================================================
class Bridge(QObject):
    new_en    = pyqtSignal(dict)
    update_zh = pyqtSignal(object, str, float)
    status    = pyqtSignal(str)
    gpu_info  = pyqtSignal(dict)      # 后台线程 → UI（避免在主线程跑 nvidia-smi）


# ============================================================
# 中英滚动同步
# ============================================================
class SyncScroller:
    def __init__(self, src, dst):
        self.src, self.dst = src, dst
        self._lock = False
        src.verticalScrollBar().valueChanged.connect(self._on_src)

    def _on_src(self, _):
        if self._lock: return
        self._lock = True
        try:
            top = self.src.cursorForPosition(QPoint(0, 0)).blockNumber()
            blk = self.dst.document().findBlockByNumber(top)
            if blk.isValid():
                cur  = QTextCursor(blk)
                rect = self.dst.cursorRect(cur)
                sb   = self.dst.verticalScrollBar()
                sb.setValue(sb.value() + rect.top())
        finally:
            self._lock = False


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR.parent).mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("会议同传 · Physics EN→ZH")
        self.resize(1360, 840)
        self.setStyleSheet(STYLE)

        # 设置面板
        self.settings = Settings(SETTINGS_PATH)
        self.glossary = load_glossary(GLOSSARY_PATH)

        self.pm = PowerManager()
        self.profile_name = self.pm.profile_name()
        self.profile = dict(PROFILES[self.profile_name])
        self._apply_settings_to_profile()

        self.store = SessionStore(DATA_DIR)
        self.store.load_all()
        self.current_session = None

        # 运行状态
        self.recording     = False
        self._pending      = 0
        self._block_map    = {}          # rid -> 中文视图 block 号
        self.stop_event    = threading.Event()
        self.recording_ref = [False]
        self.level_ref     = [0.0]
        self._gpu_thread   = None        # GPU 状态查询线程（见 _update_status_right）
        self._session_dirty = False      # 会话有改动待落盘（见 _flush_session）

        self.audio_q = queue.Queue(maxsize=400)
        # 语音段队列：有上限，但满了是「把最旧的两段合并」而不是丢弃 ——
        # 音频少一个采样，转写内容就永久缺失了（见 audio.SegmentQueue）
        self.seg_q   = SegmentQueue(maxlen=48, on_merge=self._on_seg_merge)
        # 待翻译文本队列保持无上限：每项只有几十字节，而且英文文本在入队
        # 之前就已经写进会话了，翻译晚一点不影响「记录必须完整」
        self.text_q  = queue.Queue()

        self.bridge = Bridge()
        self.bridge.new_en.connect(self.on_new_en)
        self.bridge.update_zh.connect(self.on_update_zh)
        self.bridge.status.connect(self.on_status)
        self.bridge.gpu_info.connect(self._on_gpu_info)

        self._load_app_icon()
        self._build_ui()
        self._apply_display_settings()
        self._refresh_session_list()
        self._show_welcome()
        self._update_action_ui()

        self._pm_timer = QTimer(self)
        self._pm_timer.timeout.connect(self._check_power)
        self._pm_timer.start(2000)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_right)
        self._status_timer.start(1500)

        # 会话落盘节流：改成「标记变脏 + 定时落盘」，不再每次新增/更新都整体
        # 重写一遍 JSON（长会议下那是 O(n²) 的写盘量）。界面显示依旧是即时的，
        # 1.5 秒只影响崩溃时最多丢多少内容。
        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self._flush_session)
        self._save_timer.start(1500)

    # ---------- 应用图标 ----------
    def _load_app_icon(self):
        for name in ("app.ico", "app.png"):
            p = ASSETS_DIR / name
            if p.exists():
                icon = QIcon(str(p))
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    print(f"[Main] 应用图标: {p}", flush=True)
                    return
        self.setWindowIcon(svg_icon("logo", 64, "#2563eb"))

    # ---------- 设置 -> profile ----------
    def _apply_settings_to_profile(self):
        batt = self.profile_name == "battery"
        key = "asr_model_battery" if batt else "asr_model"
        self.profile["asr_model"] = self.settings.get(key)
        self.profile["silence_ms"] = int(self.settings.get("silence_ms", 600))
        self.profile["max_seg_s"]  = int(self.settings.get("max_seg_s", 20))

    def _apply_display_settings(self):
        """把「设置 → 显示」里的字号 / 字体应用到中英两个文本框。

        【字号改了没反应的真正原因】
        Qt 样式表里的字体声明，优先级高于 QWidget.setFont()。STYLE 里有
            * { font-family: ... }          → 把英/中文字体盖掉
            QTextEdit { font-size: 14px }   → 把字号盖掉
        实测：调用 setFont(QFont("Arial", 20)) 之后，
              widget.font() 依旧是 (Segoe UI, -1)  —— 设置完全没生效。

        所以除了 setFont()，还必须往窗口样式表末尾追加 #objectName 规则：
        ID 选择器的优先级高于 `*` 和 `QTextEdit`，这样才真正压得住。
        用 pt（而不是 px）是为了和 QFont(family, size) 的语义保持一致。
        """
        base = int(self.settings.get("font_size", 14))
        en_font = _clean_font_name(self.settings.get("en_font"),
                                   "Times New Roman")
        zh_font = _clean_font_name(self.settings.get("zh_font"),
                                   "Microsoft YaHei")

        # setFont 让 QTextDocument 的默认字体也同步（渲染由样式表决定，
        # 但字体度量等读取 font() 的地方依赖它）
        self.en_view.setFont(QFont(en_font, base))
        self.zh_view.setFont(QFont(zh_font, base))

        self.setStyleSheet(STYLE + (
            f'QTextEdit#EnView {{ font-family: "{en_font}"; '
            f'font-size: {base}pt; }}\n'
            f'QTextEdit#ZhView {{ font-family: "{zh_font}"; '
            f'font-size: {base}pt; }}\n'
        ))

    def _find_asset(self, *names):
        for n in names:
            p = ASSETS_DIR / n
            if p.exists(): return p
        return None

    # ---------- 设置读写属性 ----------
    @property
    def audio_source(self):
        return self.settings.get("audio_source", "mic")

    @property
    def api_key(self):
        return self.settings.get("mt_api_key", "") or \
               os.environ.get("SILICONFLOW_API_KEY", "")

    @property
    def base_url(self):
        return self.settings.get("mt_base_url", "") or \
               os.environ.get("MT_BASE_URL", "https://api.siliconflow.cn/v1")

    @property
    def mt_model(self):
        return self.settings.get("mt_model", "") or \
               os.environ.get("MT_MODEL", "GLM-4-Flash-250414")

    @property
    def busy(self):
        return self.recording or self._pending > 0

    # ============================================================
    # UI
    # ============================================================
    def _build_ui(self):
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)

        self.sidebar = self._build_sidebar()
        h.addWidget(self.sidebar)

        right = QWidget(); right.setObjectName("RightArea")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)

        rv.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.welcome = self._build_welcome()
        self.content = self._build_content()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.content)
        rv.addWidget(self.stack, 1)

        h.addWidget(right, 1)
        self.setCentralWidget(central)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 左侧常驻状态文字
        self.info_lbl = QLabel("就绪")
        self.info_lbl.setObjectName("InfoLbl")
        self.status_bar.addWidget(self.info_lbl)

        # 右侧固定信息
        self.profile_lbl = QLabel(f"模式: {self.profile_name}")
        self.level_lbl = QLabel("🔊 -")
        self.gpu_lbl = QLabel("GPU: -")
        self.status_bar.addPermanentWidget(self.profile_lbl)
        self.status_bar.addPermanentWidget(self.level_lbl)
        self.status_bar.addPermanentWidget(self.gpu_lbl)

        self.follow = QCheckBox("自动跟随")
        self.follow.setChecked(True)
        self.status_bar.addPermanentWidget(self.follow)

    def _build_sidebar(self):
        bar = QFrame(); bar.setObjectName("SideBar")
        bar.setMinimumWidth(220); bar.setMaximumWidth(320)
        v = QVBoxLayout(bar)
        v.setContentsMargins(8, 10, 8, 10); v.setSpacing(8)

        row = QHBoxLayout(); row.setSpacing(4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索会话…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh_session_list)

        self.btn_side_collapse = icon_button("collapse", "折叠侧边栏",
                                              size=30, icon_size=16)
        self.btn_side_collapse.clicked.connect(self._toggle_sidebar)

        self.btn_new = icon_button("new", "新建翻译", size=30, icon_size=16)
        self.btn_new.clicked.connect(lambda: self._new_session(auto_start=False))

        row.addWidget(self.search_edit, 1)
        row.addWidget(self.btn_side_collapse)
        row.addWidget(self.btn_new)
        v.addLayout(row)

        self.history = QListWidget()
        self.history.itemClicked.connect(self._on_history_clicked)
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self._on_history_menu)
        v.addWidget(self.history, 1)
        return bar

    def _build_topbar(self):
        bar = QFrame(); bar.setObjectName("TopBar"); bar.setFixedHeight(52)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 6, 12, 6); h.setSpacing(6)

        self.btn_expand = icon_button("expand", "展开侧边栏", size=32, icon_size=18)
        self.btn_expand.clicked.connect(self._toggle_sidebar)
        self.btn_expand.setVisible(False)
        h.addWidget(self.btn_expand)

        self.title_edit = EditableTitle("新建")
        self.title_edit.editing_done.connect(self._on_title_changed)
        h.addWidget(self.title_edit, 1)

        self.btn_zh     = icon_button("zh",     "仅中文")
        self.btn_en     = icon_button("en",     "仅英文")
        self.btn_both   = icon_button("both",   "中英对照")
        self.btn_reload = icon_button("reload", "重载术语表")
        self.btn_export = icon_button("export", "导出结果")
        self.btn_settings = icon_button("settings", "设置")

        self.btn_zh.clicked.connect(lambda: self._set_content_mode("zh"))
        self.btn_en.clicked.connect(lambda: self._set_content_mode("en"))
        self.btn_both.clicked.connect(lambda: self._set_content_mode("both"))
        self.btn_reload.clicked.connect(self._reload_glossary)
        self.btn_export.clicked.connect(self._show_export_menu)
        self.btn_settings.clicked.connect(self._show_settings)

        for b in (self.btn_zh, self.btn_en, self.btn_both,
                  self.btn_reload, self.btn_export, self.btn_settings):
            h.addWidget(b)
        return bar

    def _build_welcome(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        v.addStretch(1)

        # 显示尺寸（逻辑像素）
        DISPLAY_SIZE = 320

        logo = QLabel()
        custom = self._find_asset(
            "welcome.png", "welcome.gif", "welcome.jpg", "welcome.jpeg")
        loaded = False
        if custom:
            pix = QPixmap(str(custom))
            if not pix.isNull():
                # 按屏幕 DPR 缩放，保证物理像素密度足够
                dpr = self.devicePixelRatioF()
                target = int(DISPLAY_SIZE * dpr)
                scaled = pix.scaled(
                    target, target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)  # 告诉 Qt 这是高密度图
                logo.setPixmap(scaled)
                loaded = True
        if not loaded:
            logo.setPixmap(svg_icon("logo", DISPLAY_SIZE,
                                    "#93c5fd").pixmap(DISPLAY_SIZE, DISPLAY_SIZE))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # title = QLabel("会议同传")
        # title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # title.setStyleSheet("font-size: 28px; font-weight: 700; color: #111827;")
        #
        sub = QLabel("你好，有什么需要帮你翻译的内容吗？")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size: 14px; color: #6b7280; margin-top: 8px;")

        self.welcome_btn = QPushButton("▶  开始翻译")
        self.welcome_btn.setObjectName("WelcomeBtn")
        self.welcome_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.welcome_btn.clicked.connect(
            lambda: self._new_session(auto_start=True))

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.welcome_btn)
        btn_row.addStretch(1)

        v.addWidget(logo); v.addSpacing(16)
        # v.addWidget(title);
        v.addWidget(sub); v.addSpacing(20)
        v.addLayout(btn_row); v.addStretch(2)
        return w

    def _build_content(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        self.content_split = QSplitter(Qt.Orientation.Horizontal)
        self.content_split.setHandleWidth(1)

        self.en_view = QTextEdit()
        self.en_view.setObjectName("EnView")     # _apply_display_settings 靠它定位
        self.en_view.setReadOnly(True)
        self.en_view.setFont(QFont("Times New Roman", 12))
        self.en_view.setPlaceholderText("English transcript…")

        self.zh_view = QTextEdit()
        self.zh_view.setObjectName("ZhView")
        self.zh_view.setReadOnly(True)
        self.zh_view.setFont(QFont("Microsoft YaHei", 11))
        self.zh_view.setPlaceholderText("中文翻译…")
        self.zh_view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_split.addWidget(self.en_view)
        self.content_split.addWidget(self.zh_view)
        self.content_split.setSizes([500, 500])
        v.addWidget(self.content_split, 1)

        self.sync = SyncScroller(self.en_view, self.zh_view)
        v.addWidget(self._build_bottom_bar())
        return w

    def _build_bottom_bar(self):
        bar = QWidget()
        bar.setFixedHeight(90)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 10, 20, 20)
        h.setSpacing(12)

        # 单一按钮，形状/样式随状态变化
        self.btn_action = QPushButton()
        self.btn_action.setObjectName("MicBtn")
        self.btn_action.setIcon(svg_icon("mic", 22, "#ffffff"))
        self.btn_action.setIconSize(QSize(22, 22))
        self.btn_action.setFixedSize(52, 52)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setToolTip("开始录音")
        self.btn_action.clicked.connect(self._on_action_clicked)

        h.addStretch(1)
        h.addWidget(self.btn_action)
        h.addStretch(1)
        return bar

    # ============================================================
    # 段落追加 / 更新
    # ============================================================
    def _append_paragraph(self, view, text):
        """
        在文档末尾追加一段，段落之间自动空一行。
        文档结构： [内容1] [空] [内容2] [空] [内容3] [空] ...
        返回内容所在的 block 号。
        """
        doc = view.document()
        cur = QTextCursor(doc)
        cur.movePosition(QTextCursor.MoveOperation.End)

        last_blk = doc.lastBlock()
        is_empty_doc = (doc.blockCount() == 1 and not last_blk.text())

        if is_empty_doc:
            cur.insertText(text)
            return cur.blockNumber()

        cur.insertBlock()   # 空行
        cur.insertBlock()   # 内容块
        blk_num = cur.blockNumber()
        cur.insertText(text)
        return blk_num

    def _update_paragraph(self, view, block_num, text):
        """精确替换某个 block 的内容，不动分隔符"""
        doc = view.document()
        blk = doc.findBlockByNumber(block_num)
        if not blk.isValid(): return
        cur = QTextCursor(blk)
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(text)

    # ============================================================
    # 布局自适应
    # ============================================================
    def _update_content_orientation(self):
        if not hasattr(self, "content_split"): return
        w = self.content_split.width(); h = self.content_split.height()
        if w <= 0 or h <= 0: return
        target = Qt.Orientation.Vertical if h > w else Qt.Orientation.Horizontal
        if self.content_split.orientation() != target:
            self.content_split.setOrientation(target)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_content_orientation()

    def showEvent(self, ev):
        super().showEvent(ev)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            QTimer.singleShot(50, self._update_content_orientation)

    # ============================================================
    # 侧栏
    # ============================================================
    def _toggle_sidebar(self):
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.btn_expand.setVisible(not visible)

    # ============================================================
    # 会话
    # ============================================================
    def _on_seg_merge(self, n):
        """语音段队列满了、开始合并时提示用户（内容没丢，只是识别滞后）。

        只在第 1 次和之后每 20 次提醒一次，避免刷屏。
        """
        if n == 1 or n % 20 == 0:
            self.bridge.status.emit(
                f"[警告] 识别跟不上，已合并 {n} 段音频（内容未丢失，但会滞后）")

    def _mark_dirty(self):
        """标记当前会话有改动。真正写盘交给 _flush_session 定时器。"""
        self._session_dirty = True

    def _flush_session(self, force=False):
        """把待落盘的会话写一次。

        定时器每 1.5 秒调一次（force=False，没改动就直接返回）；
        切换会话 / 重命名 / 停止 / 关闭窗口时用 force=True 立即落盘。
        """
        if not self._session_dirty and not force:
            return
        self._session_dirty = False
        if self.current_session:
            self.store.save(self.current_session)

    def _show_welcome(self):
        self._flush_session()          # 离开当前会话前先落盘
        self.current_session = None
        self.stack.setCurrentIndex(0)
        self.title_edit.setText("会议同传")
        self.title_edit.setEnabled(False)

    def _open_session(self, sess):
        self._flush_session()          # 切走前先把上一个会话写掉
        self.current_session = sess
        self.stack.setCurrentIndex(1)
        self.title_edit.setEnabled(True)
        self.title_edit.setText(sess.title)
        self._render_session(sess)
        self._refresh_session_list(select_id=sess.id)

    def _render_session(self, sess):
        self.en_view.clear()
        self.zh_view.clear()
        self._block_map.clear()
        self._pending = 0
        for rec in sess.records:
            self._append_paragraph(self.en_view, rec["en"])
            zh = rec.get("zh") or "[未完成]"
            self._append_paragraph(self.zh_view, zh)

    def _new_session(self, auto_start=False):
        if self.busy: self._stop_all()
        sess = self.store.create()
        self._refresh_session_list()
        self._open_session(sess)
        self._set_status(f"已创建新记录: {sess.title}")
        if auto_start:
            QTimer.singleShot(200, self._start_recording)

    def _refresh_session_list(self, *_, select_id=None):
        kw = self.search_edit.text().strip().lower()
        self.history.blockSignals(True)
        self.history.clear()
        current_item = None
        for sess in self.store.sessions:
            if kw and kw not in sess.title.lower():
                if not any(kw in (r.get("en","") + r.get("zh","")).lower()
                           for r in sess.records):
                    continue
            n = len(sess.records)
            ts = time.strftime("%m-%d %H:%M", time.localtime(sess.created_at))
            item = QListWidgetItem(f"{sess.title}\n{ts} · {n} 条")
            item.setData(Qt.ItemDataRole.UserRole, sess.id)
            self.history.addItem(item)
            if (select_id and sess.id == select_id) or \
               (not select_id and self.current_session and
                sess.id == self.current_session.id):
                current_item = item
        self.history.blockSignals(False)
        if current_item:
            self.history.setCurrentItem(current_item)
            self.history.scrollToItem(current_item)

    def _on_history_clicked(self, item):
        sid = item.data(Qt.ItemDataRole.UserRole)
        sess = next((s for s in self.store.sessions if s.id == sid), None)
        if sess:
            if self.busy: self._stop_all()
            self._open_session(sess)

    def _on_history_menu(self, pos):
        item = self.history.itemAt(pos)
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        sess = next((s for s in self.store.sessions if s.id == sid), None)
        if not sess: return
        menu = QMenu(self)
        act = QAction("删除此记录", self)
        act.triggered.connect(lambda: self._delete_session(sess))
        menu.addAction(act)
        menu.exec(self.history.mapToGlobal(pos))

    def _delete_session(self, sess):
        r = QMessageBox.question(self, "删除记录", f"确定删除「{sess.title}」？")
        if r != QMessageBox.StandardButton.Yes: return
        if self.current_session is sess:
            if self.busy: self._stop_all()
            self._show_welcome()
        self.store.delete(sess)
        self._refresh_session_list()

    def _on_title_changed(self, new_title):
        if not self.current_session: return
        new_title = new_title.strip() or self.current_session.title
        if new_title == self.current_session.title: return
        self.current_session.title = new_title
        self._flush_session(force=True)      # 重命名是显式操作，立即落盘
        self._refresh_session_list(select_id=self.current_session.id)
        self._set_status(f"已重命名为: {new_title}")

    # ============================================================
    # 视图模式
    # ============================================================
    def _set_content_mode(self, mode):
        if mode == "both":
            self.en_view.setVisible(True); self.zh_view.setVisible(True)
            self.content_split.setSizes([500, 500])
        elif mode == "zh":
            self.en_view.setVisible(False); self.zh_view.setVisible(True)
        elif mode == "en":
            self.zh_view.setVisible(False); self.en_view.setVisible(True)

    # ============================================================
    # 录音 / 翻译 状态机
    # ============================================================
    def _drain(self, q):
        while True:
            try: q.get_nowait()
            except queue.Empty: break

    def _start_worker(self, name, target, *args):
        """起一个后台线程，并把线程里蹦出来的异常报回界面。

        原来这些线程没有任何兜底：设备打不开（没麦克风、没有默认扬声器、
        回环设备被占用）或者找不到 VAD 权重时，线程会**静默死掉**，
        界面还停在「录音中」，用户完全不知道为什么没反应。
        """
        def runner():
            try:
                target(*args)
            except Exception as e:
                traceback.print_exc()
                self.bridge.status.emit(f"[错误] {name}线程退出: {e}")
        t = threading.Thread(target=runner, daemon=True, name=name)
        t.start()
        return t

    def _on_action_clicked(self):
        """单一按钮：根据状态分派"""
        if self.recording:
            self._stop_recording()
        elif self._pending > 0:
            self._stop_all()
        else:
            # 空闲：开始录音
            if not self.current_session:
                self._new_session(auto_start=False)
            self._start_recording()

    def _start_recording(self):
        if self.recording or self._pending > 0: return
        if not self.current_session:
            self._new_session(auto_start=False)
        if not self.api_key:
            QMessageBox.warning(self, "缺少 API Key",
                                "请在 设置 中配置 API Key")
            return

        self._drain(self.audio_q)
        self._drain(self.seg_q)
        self._drain(self.text_q)

        self.stop_event = threading.Event()
        self.recording_ref[0] = True
        self.level_ref[0] = 0.0

        self.translator = Translator(self.api_key, self.base_url,
                                     self.mt_model, self.glossary)

        src = self.audio_source
        cap = capture_loopback if src == "loopback" else capture_mic
        print(f"[Main] 输入源: {src}", flush=True)
        self._start_worker("录音", cap, self.audio_q, self.stop_event,
                           self.recording_ref, self.level_ref)

        self._start_worker("VAD", vad_loop, self.audio_q, self.seg_q,
                           self.profile, self.stop_event, self.recording_ref)

        self.asr = ASRWorker(
            self.seg_q, self.text_q, self.profile,
            self.translator.asr_prompt(), self.stop_event,
            self.recording_ref, self.bridge,
            on_ready=lambda n: self.bridge.status.emit("ASR 就绪"),
            on_error=lambda e: self.bridge.status.emit(f"[错误] {e}"),
        )
        self.asr.start()

        self._start_worker("翻译", mt_loop, self.text_q, self.bridge,
                           self.translator, self.stop_event,
                           self.recording_ref)

        self.recording = True
        self._update_action_ui()
        self._set_status("开始录音…")

    def _stop_recording(self):
        """只停录音，翻译继续跑完"""
        if not self.recording: return
        self.recording_ref[0] = False
        self.recording = False
        self._update_action_ui()
        self._set_status("已停止录音，等待剩余翻译…")

    def _stop_all(self):
        """强制中断一切"""
        self.stop_event.set()
        self.recording_ref[0] = False
        self._drain(self.audio_q); self._drain(self.seg_q); self._drain(self.text_q)
        for rid, zh_blk in list(self._block_map.items()):
            self._update_paragraph(self.zh_view, zh_blk, "[已取消]")
        self._block_map.clear()
        self._pending = 0
        self.recording = False
        self._update_action_ui()
        self._flush_session(force=True)      # 停止时确保内容已落盘
        self._set_status("已停止所有翻译")

    def _update_action_ui(self):
        """单一按钮：三种状态，形状和文字都不同"""
        if self.recording:
            # 录音中：红色圆形 + 停止图标
            self.btn_action.setObjectName("StopRecBtn")
            self.btn_action.setIcon(svg_icon("stop", 22, "#ffffff"))
            self.btn_action.setIconSize(QSize(22, 22))
            self.btn_action.setText("")
            self.btn_action.setFixedSize(52, 52)
            self.btn_action.setToolTip("停止录音（翻译继续）")
        elif self._pending > 0:
            # 停止录音后 MT 未跑完：红色圆角矩形 + 文字
            self.btn_action.setObjectName("StopMtBtn")
            self.btn_action.setIcon(QIcon())  # 无图标
            self.btn_action.setText("停止翻译")
            self.btn_action.setFixedSize(160, 46)
            self.btn_action.setToolTip("中断所有翻译")
        else:
            # 空闲：蓝色圆形 + 麦克风图标
            self.btn_action.setObjectName("MicBtn")
            self.btn_action.setIcon(svg_icon("mic", 22, "#ffffff"))
            self.btn_action.setIconSize(QSize(22, 22))
            self.btn_action.setText("")
            self.btn_action.setFixedSize(52, 52)
            self.btn_action.setToolTip("开始录音")

        self.btn_action.style().unpolish(self.btn_action)
        self.btn_action.style().polish(self.btn_action)

    # ============================================================
    # 数据流
    # ============================================================
    def on_new_en(self, rec):
        if not self.current_session: return
        rid = rec["rid"]

        self.current_session.records.append({
            "rid": rid, "t": rec["t"], "en": rec["en"],
            "zh": "", "asr_dt": rec["asr_dt"], "mt_dt": 0.0,
        })

        # 英文立即显示
        self._append_paragraph(self.en_view, rec["en"])
        # 中文占位
        zh_blk = self._append_paragraph(self.zh_view, "翻译中...")
        self._block_map[rid] = zh_blk
        self._pending += 1

        self._mark_dirty()                   # 交给 _flush_session 节流落盘
        self._refresh_session_list(select_id=self.current_session.id)

        if self.follow.isChecked():
            self.en_view.verticalScrollBar().setValue(
                self.en_view.verticalScrollBar().maximum())

        self._update_action_ui()
        self._set_status(f"ASR {rec['asr_dt']:.2f}s")

    def on_update_zh(self, rid, zh, mt_dt):
        if not self.current_session: return
        zh_blk = self._block_map.pop(rid, None)
        if zh_blk is None:
            print(f"[Main] update_zh: rid={rid} 未找到对应段落", flush=True)
            return
        self._update_paragraph(self.zh_view, zh_blk, zh)

        for rec in self.current_session.records:
            if rec.get("rid") == rid:
                rec["zh"] = zh
                rec["mt_dt"] = mt_dt
                break

        self._pending = max(0, self._pending - 1)
        self._mark_dirty()                   # 同上，节流落盘
        self._update_action_ui()
        self._set_status(f"MT {mt_dt:.2f}s")

    def on_status(self, msg):
        self._set_status(msg)

    def _set_status(self, msg):
        self.info_lbl.setText(msg)

    def _show_settings(self):
        print("[DBG] 进入 _show_settings", flush=True)
        if self.busy:
            QMessageBox.information(self, "请先停止",
                                    "请先停止录音和翻译再修改设置")
            return
        print("[DBG] 构造 SettingsDialog", flush=True)
        dlg = SettingsDialog(self.settings, GLOSSARY_PATH, self)
        print("[DBG] SettingsDialog 构造完成，准备 exec", flush=True)
        if dlg.exec():
            print("[DBG] exec 返回 OK", flush=True)
            self._apply_settings()
        else:
            print("[DBG] exec 返回 Cancel", flush=True)

    def _apply_settings(self):
        self._apply_settings_to_profile()
        self.glossary = load_glossary(GLOSSARY_PATH)
        self._apply_display_settings()
        self._set_status("设置已保存")
        print(f"[Main] 设置已应用: source={self.audio_source}, "
              f"model={self.mt_model}, font={self.settings.get('font_size')}",
              flush=True)

    # ============================================================
    # 术语 / 导出
    # ============================================================
    def _reload_glossary(self):
        try:
            self.glossary = load_glossary(GLOSSARY_PATH)
            if self.recording:
                self.translator = Translator(self.api_key, self.base_url,
                                             self.mt_model, self.glossary)
            self._set_status("术语表已重新加载")
        except Exception as e:
            QMessageBox.warning(self, "术语表错误", str(e))

    def _show_export_menu(self):
        records = self.current_session.records if self.current_session else []
        if not records:
            QMessageBox.information(self, "无内容", "当前记录为空")
            return
        menu = QMenu(self)
        for fmt, label in (("docx", "Word (.docx)"),
                            ("pdf",  "PDF (.pdf)"),
                            ("md",   "Markdown (.md)")):
            sub = menu.addMenu(label)
            for key, name in MODES.items():
                act = sub.addAction(name)
                act.triggered.connect(lambda _, f=fmt, k=key: self._export(f, k))
        pos = self.btn_export.mapToGlobal(
            QPoint(0, self.btn_export.height() + 4))
        menu.exec(pos)

    def _export(self, fmt, mode):
        if not self.current_session: return
        ext = {"docx": "docx", "pdf": "pdf", "md": "md"}[fmt]
        base = self.current_session.title.replace("/", "_").replace("\\", "_")
        path, _ = QFileDialog.getSaveFileName(
            self, f"导出 {ext.upper()}",
            f"{base}_{mode}.{ext}", f"{ext.upper()} (*.{ext})")
        if not path: return
        try:
            EXPORTERS[fmt](self.current_session.records, path, mode)
            self._set_status(f"已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ============================================================
    # 电源 / 状态
    # ============================================================
    def _check_power(self):
        self.pm.set_power_limit(self.profile["gpu_power_w"])
        name = self.pm.profile_name()
        if name != self.profile_name:
            self.profile_name = name
            self.profile = dict(PROFILES[name])
            self._apply_settings_to_profile()
            self.profile_lbl.setText(f"模式: {name}")
            self.pm.set_power_limit(self.profile["gpu_power_w"])
            self._set_status(f"电源切换 → {name}")

    def _update_status_right(self):
        rms = self.level_ref[0]
        bars = "▁▂▃▄▅▆▇█"
        if self.recording:
            if rms > 1e-6:
                import math
                db = 20 * math.log10(rms)
                # dB（-50~0）映射到 0-7
                idx = max(0, min(7, int((db + 50) / 50 * 8)))
            else:
                db, idx = -60.0, 0
            self.level_lbl.setText(f"🔊 {bars[idx]} {db:5.1f}dB")
        else:
            self.level_lbl.setText("🔊 -")

        # GPU 状态：nvidia-smi 单次要 60~80ms，绝不能在 GUI 线程上跑 ——
        # 否则每 1.5 秒界面就卡一下（滚动、输入都会顿）。
        # 丢给后台线程，结果通过信号回主线程刷新。
        if self._gpu_thread is None or not self._gpu_thread.is_alive():
            self._gpu_thread = threading.Thread(
                target=self._poll_gpu_info, daemon=True, name="gpuinfo")
            self._gpu_thread.start()

    def _poll_gpu_info(self):
        """后台线程：查一次 GPU 状态（异常一律吞掉，状态栏不重要）"""
        try:
            info = self.pm.gpu_info(max_age=1.0)
        except Exception:
            info = None
        if info:
            self.bridge.gpu_info.emit(info)

    def _on_gpu_info(self, info):
        """刷新 GPU 状态。字段可能是 None —— nvidia-smi 对不支持的项返回 [N/A]，
        以前正是这个让状态栏永远停在「GPU: -」（详见 power.gpu_info）。"""
        seg = []
        if info.get("temp") is not None:
            seg.append(f"{info['temp']}°C")
        if info.get("power") is not None:
            seg.append(f"{info['power']:.0f}W")
        if info.get("util") is not None:
            seg.append(f"{info['util']}%")
        self.gpu_lbl.setText("GPU " + " · ".join(seg) if seg else "GPU: -")

    def closeEvent(self, ev):
        if self.recording:
            self.stop_event.set()
        self.recording_ref[0] = False
        self._flush_session(force=True)      # 关闭前一定把最后的内容写盘
        super().closeEvent(ev)


# ============================================================
# 自检：SpeechTranslator.exe --selftest
# ------------------------------------------------------------
# 打包产物不依赖目标机器的 Python，所以出问题时很难看出是哪一步挂了。
# 这个模式会把关键依赖、VAD 推理、Qt 界面构造逐个跑一遍，并把报告写到
# exe 同目录的 selftest_report.txt（窗口版 exe 没有控制台，所以必须落盘）。
# 全部通过返回 0，有任何一项失败返回 1。
# ============================================================
def _selftest():
    import importlib, traceback

    lines = []
    failed = []

    # QApplication 必须**全程存活**，所以在这里建一次并用这个局部变量一直持有。
    # 坑：如果把 app 建在某个 step 函数里，函数一返回局部变量就被回收，
    # Qt 应用对象随之销毁，之后再构造 QPixmap / QWidget 会直接触发 Qt 致命
    # 错误（0xC0000409）把进程打掉 —— 表现为「自检跑到一半突然消失」。
    _app = QApplication.instance() or QApplication([])

    def say(msg=""):
        lines.append(msg)
        if sys.stdout is not None:
            try:
                print(msg, flush=True)
            except Exception:
                pass

    def step(name, fn, critical=True):
        try:
            info = fn()
        except Exception as e:
            failed.append(name)
            say(f"[{'FAIL' if critical else 'WARN'}] {name} — "
                f"{type(e).__name__}: {e}")
            for ln in traceback.format_exc().rstrip().splitlines():
                say("       " + ln)
        else:
            say(f"[ OK ] {name}" + (f" — {info}" if info else ""))

    # ---------- 环境 ----------
    say("=" * 66)
    say("会议同传 · 打包自检")
    say("=" * 66)
    say(f"frozen     : {getattr(sys, 'frozen', False)}")
    say(f"executable : {sys.executable}")
    say(f"_MEIPASS   : {getattr(sys, '_MEIPASS', '-')}")
    say(f"APP_DIR    : {_APP_DIR}")
    say(f"Python     : {sys.version.split()[0]}")
    say("-" * 66)

    # ---------- torch 是否被误打进包 ----------
    def _torch_check():
        """只做文件检查，不 import —— 否则 PyInstaller 会把 torch 又收进来。"""
        import site
        bases = []
        if getattr(sys, "frozen", False):
            bases.append(Path(getattr(sys, "_MEIPASS", _APP_DIR)))
            bases.append(_APP_DIR)
        else:
            try:
                bases += [Path(p) for p in site.getsitepackages()]
            except Exception:
                pass
        found = [b / "torch" for b in bases if (b / "torch").is_dir()]
        if found:
            return f"⚠ 仍在包内: {found[0]}"
        return "torch 不在包里 ✔"

    step("torch 已移除", _torch_check)

    # ---------- Python 依赖 ----------
    def _deps():
        mods = ["numpy", "onnxruntime", "faster_whisper", "ctranslate2",
                "soundcard", "openai", "docx", "reportlab", "cryptography",
                "psutil", "winreg"]
        bad = []
        for m in mods:
            try:
                importlib.import_module(m)
            except Exception as e:
                bad.append(f"{m}({type(e).__name__})")
        if bad:
            raise ImportError("导入失败: " + ", ".join(bad))
        return f"{len(mods)} 个模块全部可导入"

    step("第三方依赖导入", _deps)

    # ---------- VAD（ONNX，不再依赖 torch）----------
    def _vad():
        import numpy as np
        from audio import SileroVAD, vad_model_path
        p = vad_model_path()
        vad = SileroVAD(p)
        rng = np.random.default_rng(0)
        probs = []
        for _ in range(3):
            chunk = (rng.standard_normal(512) * 0.01).astype(np.float32)
            probs.append(round(float(vad(chunk, 16000)), 6))
        vad.reset_states()
        return f"{p} → probs={probs}"

    step("Silero VAD（onnxruntime）", _vad)

    # ---------- 外置 ASR 模型 ----------
    def _models():
        from config import PROFILES
        paths = sorted({v["asr_model"] for v in PROFILES.values()})
        missing = [p for p in paths if not Path(p).is_dir()]
        if missing:
            raise FileNotFoundError("找不到 ASR 模型目录: " + "; ".join(missing))
        return f"{len(paths)} 个模型目录存在（外置，不随包分发）"

    step("ASR 模型目录", _models, critical=False)

    # ---------- ASR 真机推理（CTranslate2 + CUDA + cuDNN）----------
    def _asr():
        import numpy as np
        from faster_whisper import WhisperModel
        from config import SR
        prof = PROFILES["battery"]          # 最小的模型，加载最快
        model = WhisperModel(
            prof["asr_model"], device="cuda",
            compute_type=prof["compute_type"],
            cpu_threads=prof["cpu_threads"], num_workers=1)
        # 2 秒静音，只为验证 CUDA/cuDNN/模型加载与解码整条链路
        segs, _info = model.transcribe(np.zeros(SR * 2, np.float32),
                                       language="en", beam_size=1,
                                       vad_filter=False)
        text = " ".join(s.text for s in segs).strip()
        del model
        return (f"{Path(prof['asr_model']).name} @cuda/"
                f"{prof['compute_type']} 加载+解码 OK")

    step("ASR 推理（cuda）", _asr)

    # ---------- GPU 状态解析 ----------
    def _gpu():
        """nvidia-smi 对不支持的字段返回 [N/A]，老代码 float('[N/A]') 会抛异常，
        结果整条 GPU 信息都丢掉、状态栏永远显示「GPU: -」。这里守住这个回归。"""
        from power import PowerManager
        info = PowerManager().gpu_info(max_age=0)
        if info is None:
            return "nvidia-smi 无可用输出（跳过）"
        got = ", ".join(f"{k}={v}" for k, v in info.items() if v is not None)
        return f"{got}（无效字段不会拖垮整体解析）"

    step("GPU 状态解析", _gpu, critical=False)

    # ---------- 导出（docx / pdf / md）----------
    def _export():
        import tempfile, shutil
        records = [{"rid": 1, "t": 0.0, "en": "Hello world.",
                    "zh": "你好，世界。", "asr_dt": 0.1, "mt_dt": 0.2}]
        tmp = Path(tempfile.mkdtemp(prefix="mt_selftest_"))
        try:
            made = []
            for fmt, ext in (("md", "md"), ("docx", "docx"), ("pdf", "pdf")):
                out = tmp / f"t.{ext}"
                EXPORTERS[fmt](records, str(out), "two_column")
                if not out.exists() or out.stat().st_size == 0:
                    raise RuntimeError(f"{fmt} 导出结果为空")
                made.append(f"{fmt}:{out.stat().st_size}B")
            return ", ".join(made)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    step("导出 md/docx/pdf", _export)

    # ---------- Qt 界面 ----------
    def _qt():
        from PyQt6.QtSvg import QSvgRenderer  # noqa: F401
        win = MainWindow()          # QApplication 由 _selftest 持有
        for name in SVG:
            icon = svg_icon(name, 24)
            if icon.isNull():
                raise RuntimeError(f"SVG 图标渲染失败: {name}")

        # 自定义图标目录必须真的是 assets/icons/（曾经写成 assets/icon/，
        # 结果自定义图标永远加载不到、一直静默走内置兜底）
        custom = [n for n in SVG if (ASSETS_DIR / "icons" / f"{n}.svg").exists()]
        if not custom:
            raise RuntimeError(
                f"在 {ASSETS_DIR / 'icons'} 下找不到任何图标，路径可能又错了")

        # 字号 / 字体设置必须真的生效（QSS 里的字体声明会盖掉 setFont，
        # 曾经导致这两个设置项完全无效）
        win.settings.set("font_size", 19)
        win.settings.set("en_font", "Georgia")
        win.settings.set("zh_font", "SimSun")
        win._apply_display_settings()
        for view, want in ((win.en_view, "Georgia"), (win.zh_view, "SimSun")):
            f = view.font()
            if f.family() != want or f.pointSize() != 19:
                raise RuntimeError(
                    f"显示设置没生效：期望 ({want}, 19)，"
                    f"实际 ({f.family()}, {f.pointSize()})")

        win.close()
        return (f"MainWindow + {len(SVG)} 个 SVG + {len(custom)} 个自定义图标；"
                f"字号/字体设置生效")

    step("Qt 界面 / SVG / 显示设置", _qt)

    # ---------- 设置对话框的图标路径 ----------
    def _dialog():
        """守住一个打包专属的坑：settings_dialog 以前用 Path(__file__) 定位
        assets/icons，打包后 __file__ 指向 _internal（那里没有 icons/），
        于是设置界面的上下箭头、下拉框箭头全部消失，而源码运行却正常。"""
        import re
        import settings_dialog as SD

        qss = SD.DIALOG_QSS
        if "@UP@" in qss or "@DOWN@" in qss:
            raise RuntimeError("QSS 里还有未替换的占位符")
        urls = re.findall(r'url\("([^"]+)"\)', qss)
        if not urls:
            raise RuntimeError(
                f"QSS 里没有任何箭头图标路径，icons 目录 = "
                f"{SD._assets_icons_dir()}")
        missing = [u for u in urls if not Path(u).is_file()]
        if missing:
            raise RuntimeError("箭头图标文件不存在: " + "; ".join(missing))

        # 光有文件还不够：QSS 里的 image: url(*.svg) 是交给 Qt 的 SVG 图像
        # 插件（imageformats/qsvg.dll）加载的，插件缺失时路径再对也画不出来。
        # 所以这里真加载一次，把「箭头能不能画出来」钉死。
        # 必须先确认 QApplication 还活着，再碰 QPixmap：
        # 没有存活的 QGuiApplication 时构造 QPixmap 会直接 abort。
        assert QApplication.instance() is not None, "QApplication 已不存在"
        from PyQt6.QtGui import QPixmap
        for u in urls:
            if QPixmap(u).isNull():
                raise RuntimeError(
                    f"图标文件存在但加载失败（很可能缺 qsvg 插件）: {u}")

        dlg = SD.SettingsDialog(Settings(SETTINGS_PATH), GLOSSARY_PATH)
        dlg.close()
        return (f"{len(urls)} 个箭头图标路径全部存在且可加载，"
                f"SettingsDialog 构造成功")

    step("设置对话框图标", _dialog)

    # ---------- 收尾 ----------
    say("-" * 66)
    if failed:
        say(f"结果：失败 {len(failed)} 项 → {', '.join(failed)}")
    else:
        say("结果：全部通过 ✔")

    report = _APP_DIR / "selftest_report.txt"
    try:
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        say(f"报告：{report}")
    except Exception as e:
        say(f"报告写入失败: {e}")

    return 1 if failed else 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    app = QApplication(sys.argv)
    app.setApplicationName("会议同传")
    app.setOrganizationName("MeetingTranslator")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()