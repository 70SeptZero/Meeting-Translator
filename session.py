# session.py
"""会话数据 + 本地存储"""
import json, time
from pathlib import Path


class Session:
    def __init__(self, sid: str, title: str = None,
                 created_at: float = None, records: list = None):
        self.id = sid
        self.title = title or time.strftime("%Y-%m-%d %H:%M")
        self.created_at = created_at or time.time()
        self.records = records or []      # [{"t","en","zh","asr_dt","mt_dt"}]

    def to_dict(self):
        return {
            "id":         self.id,
            "title":      self.title,
            "created_at": self.created_at,
            "records":    self.records,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d.get("title"),
                   d.get("created_at"), d.get("records", []))


class SessionStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions = []          # 按 created_at 倒序

    def load_all(self):
        self.sessions = []
        for p in self.data_dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                self.sessions.append(Session.from_dict(d))
            except Exception as e:
                print(f"[Store] 跳过 {p.name}: {e}")
        self.sessions.sort(key=lambda s: s.created_at, reverse=True)

    def create(self) -> Session:
        sid = time.strftime("%Y%m%d_%H%M%S")
        base, i = sid, 1
        while (self.data_dir / f"{sid}.json").exists():
            sid = f"{base}_{i}"; i += 1
        sess = Session(sid)
        self.sessions.insert(0, sess)
        self.save(sess)
        return sess

    def save(self, sess: Session):
        p = self.data_dir / f"{sess.id}.json"
        try:
            p.write_text(
                json.dumps(sess.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            print(f"[Store] 保存失败 {p.name}: {e}")

    def delete(self, sess: Session):
        p = self.data_dir / f"{sess.id}.json"
        try:
            if p.exists(): p.unlink()
        except Exception as e:
            print(f"[Store] 删除失败 {p.name}: {e}")
        if sess in self.sessions:
            self.sessions.remove(sess)