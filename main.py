import os, json, hmac, hashlib, time, base64, uuid, asyncio
from urllib.parse import parse_qs
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, Response, HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import text
from core import db, load_all, imgs, img_put, img_get, usage

KINDS = {"set", "meta", "cust", "prod", "inv", "exp"}
PW = os.getenv("APP_PASSWORD", "")
DAYS = 30
app = FastAPI()

# ---------- login (password from the APP_PASSWORD environment variable) ----------
def sign(exp): return hmac.new(PW.encode(), str(exp).encode(), hashlib.sha256).hexdigest()
def authed(req: Request):
    if not PW: return False
    t = req.cookies.get("sess", "")
    try:
        exp, sig = t.split(".")
        if int(exp) > time.time() and hmac.compare_digest(sig, sign(exp)): return True
    except Exception: pass
    a = req.headers.get("authorization", "")      # also allow `curl -u x:PASSWORD` (used by the email scheduler)
    if a.lower().startswith("basic "):
        try: return hmac.compare_digest(base64.b64decode(a[6:]).decode().split(":", 1)[1], PW)
        except Exception: return False
    return False

LOGIN = """<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Log in</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f4f7;font:16px system-ui,sans-serif;color:#17151c}
form{background:#fff;padding:28px;border-radius:18px;width:min(92vw,340px);border:1px solid #e8e5ed}
h1{font-size:22px;margin:0 0 16px}input{width:100%;padding:12px;border:1px solid #e8e5ed;border-radius:11px;font:inherit;margin-bottom:12px}
button{width:100%;padding:12px;border:0;border-radius:11px;background:#d6336c;color:#fff;font:inherit;font-weight:700;cursor:pointer}p{color:#d4382c;margin:0 0 12px;font-size:14px}
@media(prefers-color-scheme:dark){body{background:#0f0e12;color:#f3f1f5}form{background:#19171e;border-color:#2a2731}input{background:#0f0e12;color:#f3f1f5;border-color:#2a2731}}</style></head>
<body><form method=post action=/login><h1>Billing login</h1>@@<input type=password name=password placeholder=Password autofocus required><button>Log in</button></form></body></html>"""

@app.middleware("http")
async def gate(req: Request, call_next):
    if req.url.path == "/login" or authed(req):
        return await call_next(req)
    if req.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated"}, 401)
    return RedirectResponse("/login", 303)

@app.get("/login")
def login_page():
    return HTMLResponse(LOGIN.replace("@@", "" if PW else "<p>The server has no APP_PASSWORD set yet. Add it in your host's environment variables, then redeploy.</p>"))

@app.post("/login")
async def login(req: Request):
    pw = parse_qs((await req.body()).decode()).get("password", [""])[0]
    if PW and hmac.compare_digest(pw.encode(), PW.encode()):
        exp = int(time.time()) + DAYS * 86400
        r = RedirectResponse("/", 303)
        r.set_cookie("sess", f"{exp}.{sign(exp)}", max_age=DAYS * 86400, httponly=True, samesite="lax",
                     secure=req.headers.get("x-forwarded-proto") == "https")
        return r
    await asyncio.sleep(1)
    return HTMLResponse(LOGIN.replace("@@", "<p>Wrong password. Try again.</p>"), 401)

@app.get("/logout")
def logout():
    r = RedirectResponse("/login", 303); r.delete_cookie("sess"); return r

# ---------- app ----------
@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

@app.get("/api/all")
def get_all():
    return load_all()

@app.post("/api/sync")
async def sync(req: Request):
    b = await req.json()
    with db.begin() as c:
        def drop_imgs(ids):
            for i in ids:
                c.execute(imgs.delete().where(imgs.c.id == str(i)))
        def old_imgs(k):
            r = c.execute(text("SELECT data FROM docs WHERE key=:k"), {"k": k}).first()
            return set(json.loads(r[0]).get("imgs", [])) if r else set()
        for k in b.get("del", []):
            if k.startswith("inv:"): drop_imgs(old_imgs(k))
            c.execute(text("DELETE FROM docs WHERE key=:k"), {"k": k})
        for k, d in b.get("put", []):
            kind = k.split(":")[0]
            if kind not in KINDS or len(k) > 80:
                continue
            if kind == "inv": drop_imgs(old_imgs(k) - set(d.get("imgs", [])))
            c.execute(text("DELETE FROM docs WHERE key=:k"), {"k": k})
            c.execute(text("INSERT INTO docs (key, kind, data) VALUES (:k, :kind, :d)"),
                      {"k": k, "kind": kind, "d": json.dumps(d)})
    return {"ok": True}

@app.post("/api/img")
async def upload_img(req: Request):
    data = (await req.json()).get("data", "")
    if not data.startswith("data:image/") or len(data) > 2_500_000:
        raise HTTPException(400, "Bad image")
    return {"id": img_put(base64.b64decode(data.split(",", 1)[1]))}

@app.get("/api/img/{iid}")
def get_img(iid: str):
    b = img_get(iid)
    if not b: raise HTTPException(404)
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})

@app.get("/api/usage")
def get_usage():
    return usage()

@app.get("/api/invoice/{iid}.pdf")
def invoice_pdf(iid: str, dl: int = 0):
    from pdf import make_pdf
    out = make_pdf(iid)
    if not out: raise HTTPException(404)
    return Response(out[0], media_type="application/pdf",
                    headers={"Content-Disposition": f'{"attachment" if dl else "inline"}; filename="{out[1]}.pdf"'})

@app.get("/api/cron/{period}")
def cron(period: str, bg: BackgroundTasks):
    # Called by the free GitHub Actions schedule (see README) to email the weekly / monthly summary.
    if period not in ("weekly", "monthly"):
        raise HTTPException(404)
    from summary import send_summary
    bg.add_task(send_summary, period)
    return {"queued": period}
