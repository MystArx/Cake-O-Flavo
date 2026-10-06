import os, io, csv, smtplib
from html import escape
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from core import load_all

TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Kolkata"))
f = lambda v: float(v or 0)

def total(i):
    s = sum(f(t.get("qty")) * f(t.get("rate")) for t in i.get("items", []))
    x = max(0, s - f(i.get("disc")))
    return x + x * f(i.get("tax")) / 100

def window(period):
    t = datetime.now(TZ).date()
    if period == "weekly":                      # the 7 days before today
        return t - timedelta(days=7), t
    first = t.replace(day=1)                    # the whole previous month
    return (first - timedelta(days=1)).replace(day=1), first

def build(period):
    a, b = window(period)
    d = load_all()
    name = (d["set"] or {}).get("name", "Bakery")
    cur = (d["set"] or {}).get("cur", "₹")
    inrange = lambda x: a.isoformat() <= x.get("date", "") < b.isoformat()
    inv = sorted([i for i in d["inv"] if inrange(i)], key=lambda i: (i.get("date", ""), i.get("no", 0)))
    exp = [e for e in d["exp"] if inrange(e)]
    paid = sum(total(i) for i in inv if i.get("status") == "paid")
    unpaid = sum(total(i) for i in inv if i.get("status") != "paid")
    spent = sum(f(e.get("amt")) for e in exp)
    prods, custs = {}, {}
    for i in inv:
        for t in i["items"]:
            p = prods.setdefault(t.get("name") or "?", [0, 0])
            p[0] += f(t.get("qty")); p[1] += f(t.get("qty")) * f(t.get("rate"))
        c = i.get("cname") or "Walk-in"
        custs[c] = custs.get(c, 0) + total(i)
    m = lambda v: f"{cur}{v:,.2f}"
    top = lambda dct, k: sorted(dct.items(), key=k, reverse=True)[:5]
    tp = top(prods, lambda kv: kv[1][1]); tc = top(custs, lambda kv: kv[1])
    last = b - timedelta(days=1)
    lines = [f"{name}: {period} summary, {a} to {last}", "",
             f"Orders: {len(inv)}", f"Income (paid): {m(paid)}", f"Unpaid: {m(unpaid)}",
             f"Expenses: {m(spent)}", f"Profit: {m(paid - spent)}", "", "Top products:"]
    lines += [f"  {n}: {q:g} sold, {m(r)}" for n, (q, r) in tp] or ["  none"]
    lines += ["", "Top customers:"] + ([f"  {n}: {m(v)}" for n, v in tc] or ["  none"])
    rows = "".join(f"<tr><td>INV-{int(i.get('no', 0)):06d}</td><td>{i.get('date')}</td><td>{escape(i.get('cname') or 'Walk-in')}</td><td>{i.get('status')}</td><td align=right>{m(total(i))}</td></tr>" for i in inv)
    html = (f"<h2>{escape(name)}: {period} summary</h2><p>{a} to {last}</p>"
            f"<p>Orders: <b>{len(inv)}</b><br>Income (paid): <b>{m(paid)}</b><br>Unpaid: <b>{m(unpaid)}</b><br>Expenses: <b>{m(spent)}</b><br>Profit: <b>{m(paid - spent)}</b></p>"
            f"<h3>Top products</h3><ul>{''.join(f'<li>{escape(n)}: {q:g} sold, {m(r)}</li>' for n, (q, r) in tp) or '<li>none</li>'}</ul>"
            f"<h3>Top customers</h3><ul>{''.join(f'<li>{escape(n)}: {m(v)}</li>' for n, v in tc) or '<li>none</li>'}</ul>"
            f"<h3>Orders</h3><table cellpadding=6 border=1 style='border-collapse:collapse'><tr><th>No</th><th>Date</th><th>Customer</th><th>Status</th><th>Total</th></tr>{rows}</table>")
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["invoice", "date", "customer", "status", "items", "total"])
    for i in inv:
        w.writerow([f"INV-{int(i.get('no', 0)):06d}", i.get("date"), i.get("cname") or "Walk-in", i.get("status"),
                    "; ".join(f"{t.get('qty')} x {t.get('name')}" for t in i["items"]), round(total(i), 2)])
    return dict(subject=f"{name} {period} summary ({a} to {last})", text="\n".join(lines), html=html,
                csv=buf.getvalue().encode(), fname=f"orders_{a}_{last}.csv")

def send_summary(period):
    r = build(period)
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = r["subject"], user, os.environ["MAIL_TO"]
    msg.set_content(r["text"]); msg.add_alternative(r["html"], subtype="html")
    msg.add_attachment(r["csv"], maintype="text", subtype="csv", filename=r["fname"])
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls(); s.login(user, os.environ["SMTP_PASS"]); s.send_message(msg)
    return f"sent {period} summary"
