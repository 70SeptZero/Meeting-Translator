# build.py
"""
一键打包（只有 bundle 一种模式）：

    python build.py            # 打包
    python build.py --bundle   # 同上（保留这个参数只是为了兼容旧命令）

产物：
    dist/SpeechTranslator/           ← 可直接运行的目录
    release/SpeechTranslator-bundle.zip

打完的包**不依赖目标机器上的 Python**：PyInstaller 已经把 CPython 解释器
和全部三方依赖塞进 dist/SpeechTranslator/ 里，拷过去双击
SpeechTranslator.exe 就能用。

注意：ASR 模型仍然是外置的，路径见 config.py 的 MODELS_DIR
（默认 E:\\models），不随包分发。
"""
import argparse, shutil, subprocess, sys, zipfile
from pathlib import Path

ROOT        = Path(__file__).parent
RELEASE_DIR = ROOT / "release"
DIST_NAME   = "SpeechTranslator"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc",
                                 ".DS_Store", "*.log")

# 需要放到 exe 同目录（用户可见 / 可替换）的东西
COPY_DIRS  = ["assets"]
COPY_FILES = ["glossary.json", "README.md", "LICENSE"]


def _zip(src_dir: Path, zip_path: Path, root_name: str):
    """把 src_dir 内容打进 zip，包内顶层目录为 root_name"""
    print(f"[zip] → {zip_path.name}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in src_dir.rglob("*"):
            if f.is_file():
                z.write(f, Path(root_name) / f.relative_to(src_dir))


def build_bundle():
    # 清旧产物
    for d in (ROOT / "dist", ROOT / "build"):
        if d.exists():
            print(f"[clean] {d}")
            shutil.rmtree(d)

    print("[pyinstaller] 打包中（5-20 分钟）…")
    # 用当前解释器跑 PyInstaller，保证用的是这个环境里的依赖，
    # 不依赖 PATH 上有没有 pyinstaller / 有没有激活虚拟环境。
    cmd = [sys.executable, "-m", "PyInstaller",
           "--clean", "--noconfirm", "build.spec"]
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("[ERROR] PyInstaller 失败"); return

    dist_dir = ROOT / "dist" / DIST_NAME
    if not dist_dir.exists():
        print(f"[ERROR] 未找到 {dist_dir}"); return

    # 把 assets / glossary / 说明档挪到 exe 同目录
    for name in COPY_DIRS:
        src = ROOT / name
        dst = dist_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst, ignore=IGNORE)

    for name in COPY_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, dist_dir / name)

    (dist_dir / "data" / "sessions").mkdir(parents=True, exist_ok=True)

    # 简单体积报告
    total = sum(f.stat().st_size
                for f in dist_dir.rglob("*") if f.is_file())
    print(f"[size] {DIST_NAME} = {total / 1024 / 1024:.1f} MB")

    _zip(dist_dir, RELEASE_DIR / f"{DIST_NAME}-bundle.zip", DIST_NAME)
    print("✅ bundle 打包完成（目标机器无需安装 Python，双击 exe 即用）\n")


def main():
    # Windows 控制台默认是 GBK，直接 print 中文/emoji 会抛 UnicodeEncodeError
    # 把已经打好的包白白判成失败，所以这里强制 UTF-8 输出。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser()
    p.add_argument("--bundle", action="store_true",
                   help="打包完整版（现在这是唯一模式，参数可省略）")
    p.parse_args()

    RELEASE_DIR.mkdir(exist_ok=True)
    build_bundle()
    print(f"📦 产物：{RELEASE_DIR.resolve()}")


if __name__ == "__main__":
    main()
