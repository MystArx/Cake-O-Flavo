import os, json
import uuid
from sqlalchemy import create_engine, text, Table, Column, String, LargeBinary, MetaData

url = os.getenv("DATABASE_URL", "sqlite:///bakery.db")
for old in ("postgres://", "postgresql://"):
    if url.startswith(old):
        url = "postgresql+psycopg2://" + url[len(old):]
db = create_engine(url, pool_pre_ping=True, pool_recycle=300)
with db.begin() as c:
    c.execute(text("CREATE TABLE IF NOT EXISTS docs (key VARCHAR(80) PRIMARY KEY, kind VARCHAR(20), data TEXT)"))

meta = MetaData()
imgs = Table("imgs", meta, Column("id", String(32), primary_key=True), Column("data", LargeBinary))
meta.create_all(db)

def img_put(b):
    i = uuid.uuid4().hex[:12]
    with db.begin() as c:
        c.execute(imgs.insert().values(id=i, data=b))
    return i

def img_get(i):
    with db.connect() as c:
        r = c.execute(imgs.select().where(imgs.c.id == str(i))).first()
    return bytes(r.data) if r else None

def usage():
    with db.connect() as c:
        if db.dialect.name == "postgresql":
            b = c.execute(text("SELECT pg_database_size(current_database())")).scalar()
        else:
            b = c.execute(text("SELECT (SELECT page_count FROM pragma_page_count()) * (SELECT page_size FROM pragma_page_size())")).scalar()
        n = c.execute(text("SELECT count(*) FROM imgs")).scalar()
    return {"bytes": int(b or 0), "photos": int(n or 0), "limit": int(float(os.getenv("STORAGE_LIMIT_MB", "500")) * 1048576)}

def load_all():
    out = {"set": None, "n": 1, "cust": [], "prod": [], "inv": [], "exp": []}
    with db.connect() as c:
        for kind, data in c.execute(text("SELECT kind, data FROM docs WHERE kind != 'img' ORDER BY key")):
            d = json.loads(data)
            if kind == "set": out["set"] = d
            elif kind == "meta": out["n"] = d.get("n", 1)
            elif kind in out: out[kind].append(d)
    return out
