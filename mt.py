# mt.py
import time, queue, json
from openai import OpenAI
from pathlib import Path


def load_glossary(path):
    path = Path(path)
    if not path.exists():
        print(f"[MT] 术语表不存在: {path}，使用空术语表", flush=True)
        return {"terms": {}, "fixups": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[MT] 术语表读取失败: {e}，使用空术语表", flush=True)
        return {"terms": {}, "fixups": {}}


# mt.py —— Translator 类替换
class Translator:
    def __init__(self, api_key, base_url, model, glossary):
        self.client  = OpenAI(api_key=api_key, base_url=base_url,
                              timeout=20.0, max_retries=0)
        self.model   = model
        self.terms   = glossary.get("terms", {})
        self.fixups  = glossary.get("fixups", {})

        # 按长度降序排列，优先匹配长术语（避免 "quantum" 抢先匹配 "quantum chromodynamics"）
        self._terms_sorted = sorted(self.terms.items(),
                                     key=lambda kv: -len(kv[0]))

        self.base_sys = (
            "你是物理学会议的专业同声传译。把用户给出的英文翻译成简洁、"
            "口语化的中文，符合中文会议表达习惯。要求：\n"
            "1. 术语使用物理学界通用译名；\n"
            "2. 公式、变量符号、人名、单位保留原文；\n"
            "3. 只输出译文，不要任何解释、前后缀或引号。"
        )

    def asr_prompt(self):
        """Whisper 的 initial_prompt 仍保留全量术语，但截断长度"""
        terms = " ".join(k for k, _ in self._terms_sorted)
        return ("Physics conference talk. Technical terms: " + terms)[:1200]

    def _pick_terms(self, text: str):
        """只挑当前段落里出现的术语"""
        tl = text.lower()
        hit = []
        for en, zh in self._terms_sorted:
            if en.lower() in tl:
                hit.append((en, zh))
                if len(hit) >= 30:      # 一段里最多 30 条，防极端情况
                    break
        return hit

    def _build_sys(self, en_text: str) -> str:
        hit = self._pick_terms(en_text)
        if not hit:
            return self.base_sys
        gloss = "\n".join(f"  {k} → {v}" for k, v in hit)
        return f"{self.base_sys}\n本段涉及的术语：\n{gloss}"

    def translate(self, text):
        t0 = time.time()
        first_dt = None
        chunks = []
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_sys(text)},
                    {"role": "user",   "content": text},
                ],
                temperature=0.2, max_tokens=1024, stream=True,
            )
            for chunk in stream:
                if first_dt is None:
                    first_dt = time.time() - t0
                d = chunk.choices[0].delta.content
                if d: chunks.append(d)
        except Exception as e:
            print(f"[MT] 请求失败 ({time.time()-t0:.2f}s): {e}", flush=True)
            raise
        zh = "".join(chunks).strip()
        print(f"[MT] 首token {first_dt:.2f}s / 总 {time.time()-t0:.2f}s", flush=True)
        for k, v in self.fixups.items():
            zh = zh.replace(k, v)
        return zh


def mt_loop(text_q, bridge, translator, stop_event, recording_ref):
    """
    recording_ref: [bool]，False 且队列空时线程自动退出
    """
    while not stop_event.is_set():
        try:
            item = text_q.get(timeout=0.3)
        except queue.Empty:
            if not recording_ref[0] and text_q.empty():
                break
            continue

        rid, en, asr_dt = item
        try:
            t0 = time.time()
            zh = translator.translate(en)
            mt_dt = time.time() - t0
            print(f"[MT] {en[:40]} → {zh[:40]} ({mt_dt:.2f}s)", flush=True)
            bridge.update_zh.emit(rid, zh, mt_dt)
        except Exception as e:
            print(f"[MT] 错误: {e}", flush=True)
            bridge.update_zh.emit(rid, f"[翻译失败: {e}]", 0.0)

    print("[MT] 退出", flush=True)