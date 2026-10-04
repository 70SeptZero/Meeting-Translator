# settings_dialog.py
"""设置对话框：左侧导航 + 右侧内容"""
import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QPushButton, QLabel,
    QFileDialog, QMessageBox, QPlainTextEdit,
    QListWidget, QListWidgetItem, QStackedWidget, QFrame,
)


# ============================================================
# 图标路径
# ------------------------------------------------------------
# 【打包后会失效的写法，别再改回去】
# 以前这里直接写 Path(__file__).resolve().parent / "assets" / "icons"。
# 源码运行没问题，但打包后 __file__ 指向的是 PyInstaller 的解包目录
# （sys._MEIPASS 即 _internal/），而那里只放了 silero_vad.onnx，并没有
# icons/。于是 QSS 里的 url(...) 指到一个不存在的文件 —— 设置界面里
# 微调框的上下箭头、下拉框的箭头会**全部消失**。
# （main.py 看着没事，是因为它把 SVG 内联在代码里兜底，而且用的是 exe
#   同目录的 ASSETS_DIR；audio.py 则显式判断了 sys.frozen。）
#
# 另外：QSS 里的相对路径是按**工作目录**解析的，不是按脚本目录，
# 所以这里必须给绝对路径。
# ============================================================
def _assets_icons_dir():
    """按 exe 同目录 → _MEIPASS → 源码目录 的顺序找 assets/icons。"""
    here = Path(__file__).resolve().parent
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(Path(sys.executable).resolve().parent / "assets" / "icons")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cands.append(Path(meipass) / "assets" / "icons")
    cands.append(here / "assets" / "icons")
    for d in cands:
        if d.is_dir():
            return d
    return None


# ============================================================
# 对话框专用样式
# ============================================================
DIALOG_QSS_TEMPLATE = """
QDialog { background: #ffffff; }

QListWidget#NavList {
    background: #f9fafb;
    border: none;
    border-right: 1px solid #ececec;
    outline: none;
    padding: 10px 8px;
}
QListWidget#NavList::item {
    padding: 10px 14px;
    border-radius: 8px;
    color: #374151;
    margin: 3px 0;
    font-size: 13px;
}
QListWidget#NavList::item:hover    { background: #eef2f7; }
QListWidget#NavList::item:selected {
    background: #dbeafe; color: #1e40af; font-weight: 600;
}

QWidget#Page { background: #ffffff; }

QLabel#PageTitle {
    font-size: 16px; font-weight: 600; color: #111827;
}
QLabel#PageSub {
    font-size: 12px; color: #6b7280;
}
QLabel#HintLbl {
    color: #6b7280; font-size: 12px;
}
QLabel#HintLblMono {
    color: #6b7280; font-size: 12px; font-family: Consolas, monospace;
}

QLineEdit {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 7px 10px; font-size: 13px; color: #1f2937;
}
QLineEdit:focus { border-color: #93c5fd; }

QComboBox {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 6px 28px 6px 10px; font-size: 13px; color: #1f2937;
    min-height: 20px;
}
QComboBox:focus { border-color: #93c5fd; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: url("@DOWN@");
    width: 10px;
    height: 10px;
    margin-right: 6px;
    margin-top: 6px;
}
QComboBox::down-arrow:hover { border-top-color: #374151; }
QComboBox:hover { border-color: #93c5fd; }

QSpinBox {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 6px 26px 6px 10px; font-size: 13px; color: #1f2937;
    min-height: 20px;
}
QSpinBox:focus { border-color: #93c5fd; }

/* 上下按钮：去掉边框和背景，只留箭头 */
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 18px;
    border: none;
    background: transparent;
    padding: 0;
}
QSpinBox::up-button {
    subcontrol-position: top right;
    margin: 3px 3px 0 0;
    border-top-right-radius: 8px;
}
QSpinBox::down-button {
    subcontrol-position: bottom right;
    margin: 0 3px 3px 0;
    border-bottom-right-radius: 8px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #f3f4f6;
}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
    background: #e5e7eb;
}

/* 用 CSS 三角代替系统图标 */
QSpinBox::up-arrow {
    image: url("@UP@");
    width: 8px;
    height: 8px;
}
QSpinBox::down-arrow {
    image: url("@DOWN@");
    width: 8px;
    height: 8px;
}

QPlainTextEdit {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 10px; font-size: 12px; color: #1f2937;
}
QPlainTextEdit:focus { border-color: #93c5fd; }

QPushButton#GhostBtn {
    background: #ffffff; color: #374151;
    border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 6px 14px; font-size: 13px;
}
QPushButton#GhostBtn:hover { background: #f3f4f6; }

QPushButton#PrimaryBtn {
    background: #2563eb; color: #ffffff;
    border: none; border-radius: 8px;
    padding: 8px 24px; font-size: 13px; font-weight: 600;
}
QPushButton#PrimaryBtn:hover { background: #1d4ed8; }

QPushButton#CancelBtn {
    background: #ffffff; color: #374151;
    border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 8px 24px; font-size: 13px;
}
QPushButton#CancelBtn:hover { background: #f3f4f6; }
"""

def _build_dialog_qss():
    """把箭头图标的绝对路径填进 QSS；找不到图标就退化成系统自带箭头。"""
    icons = _assets_icons_dir()

    def _url(filename):
        if icons is not None:
            p = icons / filename
            if p.is_file():
                return f'url("{p.as_posix()}")'
        return None

    qss = DIALOG_QSS_TEMPLATE
    for token, filename in (("@UP@", "up_arrow.svg"),
                            ("@DOWN@", "down_arrow.svg")):
        real = _url(filename)
        if real is not None:
            qss = qss.replace(f'url("{token}")', real)
        else:
            # 图标缺失时把整行 image 声明删掉，让 Qt 画系统自带箭头 ——
            # 总比「箭头整个消失、用户不知道这里能点」要好
            qss = "\n".join(ln for ln in qss.splitlines() if token not in ln)
    return qss


DIALOG_QSS = _build_dialog_qss()


class SettingsDialog(QDialog):
    def __init__(self, settings, glossary_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(880, 640)
        self.setStyleSheet(DIALOG_QSS)

        self.settings = settings
        self.glossary_path = Path(glossary_path)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 主体 ----
        body = QWidget()
        body_h = QHBoxLayout(body)
        body_h.setContentsMargins(0, 0, 0, 0)
        body_h.setSpacing(0)

        # 左侧导航
        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setFixedWidth(180)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        body_h.addWidget(self.nav)

        # 右侧内容
        self.stack = QStackedWidget()
        body_h.addWidget(self.stack, 1)

        # 加页面（顺序与导航一致）
        self._add_page("音频",   "选择从哪里采集声音",           self._build_audio_page())
        self._add_page("识别",   "语音识别模型与分段参数",       self._build_asr_page())
        self._add_page("翻译",   "翻译服务 API 配置",            self._build_mt_page())
        self._add_page("显示",   "字号与字体",                   self._build_display_page())
        self._add_page("术语表", "物理专业术语对照",             self._build_glossary_page())

        root.addWidget(body, 1)

        # ---- 底部按钮 ----
        footer = QFrame()
        footer.setStyleSheet(
            "QFrame { background: #f9fafb; border-top: 1px solid #ececec; }")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(20, 12, 20, 12)
        fh.addStretch(1)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("保存")
        btn_ok.setObjectName("PrimaryBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        btn_ok.setDefault(True)

        fh.addWidget(btn_cancel)
        fh.addWidget(btn_ok)
        root.addWidget(footer)

        self.nav.setCurrentRow(0)

    # ============================================================
    # 导航辅助
    # ============================================================
    def _add_page(self, title, subtitle, content_widget):
        # 左侧项
        item = QListWidgetItem(f"  {title}")
        item.setSizeHint(QSize(0, 42))
        self.nav.addItem(item)

        # 右侧容器（标题 + 分隔线 + 内容）
        page = QWidget()
        page.setObjectName("Page")
        pv = QVBoxLayout(page)
        pv.setContentsMargins(40, 32, 40, 32)
        pv.setSpacing(4)

        h_title = QLabel(title);    h_title.setObjectName("PageTitle")
        h_sub   = QLabel(subtitle); h_sub.setObjectName("PageSub")
        pv.addWidget(h_title)
        pv.addWidget(h_sub)
        pv.addSpacing(14)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ececec;")
        pv.addWidget(sep)
        pv.addSpacing(20)

        pv.addWidget(content_widget, 1)

        self.stack.addWidget(page)

    def _on_nav_changed(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    # ============================================================
    # 表单辅助
    # ============================================================
    def _form(self):
        f = QFormLayout()
        f.setContentsMargins(0, 0, 0, 0)
        f.setHorizontalSpacing(28)
        f.setVerticalSpacing(20)      # ← 拉大行距
        f.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        f.setFormAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        f.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return f

    def _hint(self, text, mono=False):
        lbl = QLabel(text)
        lbl.setObjectName("HintLblMono" if mono else "HintLbl")
        lbl.setWordWrap(True)
        return lbl

    def _wrap_row(self, *widgets):
        """把多个控件横排，方便塞进 QFormLayout 的字段位置"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            if isinstance(x, int):
                h.addStretch(x)
            else:
                h.addWidget(x, 1 if isinstance(x, QLineEdit) else 0)
        return w

    def _ghost_btn(self, text, slot):
        b = QPushButton(text)
        b.setObjectName("GhostBtn")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ============================================================
    # 页面 1：音频
    # ============================================================
    def _build_audio_page(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        f = self._form()
        self.audio_source = QComboBox()
        self.audio_source.addItem("麦克风（现场会议 / 外放）", "mic")
        self.audio_source.addItem("系统回环（线上会议）", "loopback")
        cur = self.settings.get("audio_source", "mic")
        self.audio_source.setCurrentIndex(1 if cur == "loopback" else 0)
        f.addRow("音频来源", self.audio_source)

        v.addLayout(f)
        v.addSpacing(24)
        v.addWidget(self._hint(
            "· 麦克风：抓取现场 / 扬声器外放的声音\n"
            "· 系统回环：抓取电脑正在播放的声音，用于腾讯会议 / Zoom\n"
            "  需要确保声音播放到「默认扬声器」"))
        v.addStretch(1)
        return w

    # ============================================================
    # 页面 2：识别
    # ============================================================
    def _build_asr_page(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        f = self._form()

        self.asr_model = QLineEdit(self.settings.get("asr_model", ""))
        f.addRow("插电时模型",
                 self._wrap_row(self.asr_model,
                                self._ghost_btn("浏览",
                                    lambda: self._browse_into(self.asr_model))))

        self.asr_model_batt = QLineEdit(
            self.settings.get("asr_model_battery", ""))
        f.addRow("离电时模型",
                 self._wrap_row(self.asr_model_batt,
                                self._ghost_btn("浏览",
                                    lambda: self._browse_into(self.asr_model_batt))))

        self.silence_ms = QSpinBox()
        self.silence_ms.setRange(200, 2000); self.silence_ms.setSingleStep(50)
        self.silence_ms.setSuffix(" ms")
        self.silence_ms.setValue(int(self.settings.get("silence_ms", 600)))
        f.addRow("静音阈值", self.silence_ms)

        self.max_seg_s = QSpinBox()
        self.max_seg_s.setRange(3, 60); self.max_seg_s.setSuffix(" s")
        self.max_seg_s.setValue(int(self.settings.get("max_seg_s", 20)))
        f.addRow("单段最长", self.max_seg_s)

        v.addLayout(f)
        v.addSpacing(24)
        v.addWidget(self._hint(
            "· 静音阈值越小延迟越低，但可能把一句话切碎\n"
            "· 单段最长越大延迟越高，但识别更完整\n"
            "· 修改后需要重新开始录音才生效"))
        v.addStretch(1)
        return w

    def _browse_into(self, line_edit):
        p = QFileDialog.getExistingDirectory(
            self, "选择模型目录", line_edit.text() or "E:\\models")
        if p: line_edit.setText(p)

    # ============================================================
    # 页面 3：翻译
    # ============================================================
    def _build_mt_page(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        f = self._form()

        self.mt_base = QLineEdit(self.settings.get("mt_base_url", ""))
        f.addRow("API 地址", self.mt_base)

        self.mt_model = QLineEdit(self.settings.get("mt_model", ""))
        f.addRow("模型名称", self.mt_model)

        self.mt_key = QLineEdit(self.settings.get("mt_api_key", ""))
        self.mt_key.setEchoMode(QLineEdit.EchoMode.Password)
        show_btn = QPushButton("显示"); show_btn.setCheckable(True)
        show_btn.setObjectName("GhostBtn")
        show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        show_btn.toggled.connect(
            lambda c: self.mt_key.setEchoMode(
                QLineEdit.EchoMode.Normal if c
                else QLineEdit.EchoMode.Password))
        f.addRow("API Key", self._wrap_row(self.mt_key, show_btn))

        v.addLayout(f)
        v.addSpacing(24)

        v.addWidget(self._hint("常用配置："))
        v.addSpacing(12)

        ref = QPlainTextEdit()
        ref.setReadOnly(True)
        ref.setFont(QFont("Consolas", 10))
        ref.setPlainText(
            "Zhipu     https://open.bigmodel.cn/api/paas/v4     GLM-4-Flash-250414\n"
            "Silicon   https://api.siliconflow.cn/v1            Qwen/Qwen2.5-7B-Instruct\n"
            "DeepSeek  https://api.deepseek.com/v1              deepseek-chat"
        )
        ref.setFixedHeight(84)
        ref.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #f9fafb; border: 1px solid #ececec;"
            "  border-radius: 8px; padding: 10px; color: #374151;"
            "}")
        v.addWidget(ref)
        v.addStretch(1)
        return w

    # ============================================================
    # 页面 4：显示
    # ============================================================
    def _build_display_page(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        f = self._form()

        self.font_size = QSpinBox()
        self.font_size.setRange(9, 24)
        self.font_size.setValue(int(self.settings.get("font_size", 14)))
        f.addRow("正文字号", self.font_size)

        self.en_font = QComboBox()
        self.en_font.setEditable(True)
        self.en_font.addItems([
            "Times New Roman", "Georgia", "Cambria",
            "Arial", "Segoe UI", "Consolas",
        ])
        self.en_font.setCurrentText(
            self.settings.get("en_font", "Times New Roman"))
        f.addRow("英文字体", self.en_font)

        self.zh_font = QComboBox()
        self.zh_font.setEditable(True)
        self.zh_font.addItems([
            "Microsoft YaHei", "微软雅黑",
            "SimSun", "宋体",
            "SimHei", "黑体",
            "PingFang SC", "Source Han Sans SC",
        ])
        self.zh_font.setCurrentText(
            self.settings.get("zh_font", "Microsoft YaHei"))
        f.addRow("中文字体", self.zh_font)

        v.addLayout(f)
        v.addSpacing(24)
        v.addWidget(self._hint(
            "· 下拉框可以直接输入任意已安装字体的名称\n"
            "· 修改后立即生效，不用重启"))
        v.addStretch(1)
        return w

    # ============================================================
    # 页面 5：术语表
    # ============================================================
    def _build_glossary_page(self):
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(12)

        v.addWidget(self._hint(
            "直接编辑 JSON，保存后生效。\n"
            "terms 是术语对照，fixups 是译文修正。"))

        self.glossary_edit = QPlainTextEdit()
        self.glossary_edit.setFont(QFont("Consolas", 10))
        try:
            self.glossary_edit.setPlainText(
                self.glossary_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.glossary_edit.setPlainText(f"读取失败: {e}")
        v.addWidget(self.glossary_edit, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_fmt = QPushButton("格式化 JSON")
        btn_fmt.setObjectName("GhostBtn")
        btn_fmt.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fmt.clicked.connect(self._format_glossary)
        row.addWidget(btn_fmt)
        v.addLayout(row)
        return w

    def _format_glossary(self):
        try:
            d = json.loads(self.glossary_edit.toPlainText())
            self.glossary_edit.setPlainText(
                json.dumps(d, ensure_ascii=False, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "JSON 格式错误", str(e))

    # ============================================================
    # 保存
    # ============================================================
    def accept(self):
        s = self.settings
        s.set("audio_source",      self.audio_source.currentData())
        s.set("asr_model",         self.asr_model.text().strip())
        s.set("asr_model_battery", self.asr_model_batt.text().strip())
        s.set("silence_ms",        self.silence_ms.value())
        s.set("max_seg_s",         self.max_seg_s.value())
        s.set("mt_base_url",       self.mt_base.text().strip())
        s.set("mt_model",          self.mt_model.text().strip())
        s.set("mt_api_key",        self.mt_key.text().strip())
        s.set("font_size",         self.font_size.value())
        s.set("en_font",           self.en_font.currentText())
        s.set("zh_font",           self.zh_font.currentText())

        try:
            content = self.glossary_edit.toPlainText()
            json.loads(content)
            self.glossary_path.write_text(content, encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "术语表保存失败", f"JSON 格式错误：\n{e}")
            return

        s.save()
        super().accept()