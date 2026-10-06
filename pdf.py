import io, os, re
from datetime import datetime
from xml.sax.saxutils import escape as X
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Table, TableStyle, Paragraph, Spacer, Flowable, HRFlowable
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from core import load_all, img_get

FD = os.path.join(os.path.dirname(__file__), "fonts")
for n, f in (("R", "DejaVuSansCondensed"), ("B", "DejaVuSansCondensed-Bold"), ("BI", "DejaVuSansCondensed-BoldOblique"),
             ("I", "DejaVuSansCondensed-Oblique"), ("S", "GreatVibes-Regular")):
    if os.path.exists(f"{FD}/{f}.ttf"): pdfmetrics.registerFont(TTFont(n, f"{FD}/{f}.ttf"))
HAS_S = "S" in pdfmetrics.getRegisteredFontNames()
PINK, SOFT, MAROON, GREY = (colors.HexColor(h) for h in ("#c92a66", "#fdf0f5", "#3b0f26", "#7a6b74"))
LINE, ROW, GREEN, AMBER = (colors.HexColor(h) for h in ("#eddde5", "#fff8fb", "#178a5b", "#a75a07"))
PW, PH = A4

def P(t, font="R", size=9, align=0, color=colors.black, lead=None):
    return Paragraph(t, ParagraphStyle("x", fontName=font, fontSize=size, alignment=align, textColor=color, leading=lead or size * 1.38))

def fmt(n):
    i, d = f"{abs(float(n)):.2f}".split(".")
    if len(i) > 3: i = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", i[:-3]) + "," + i[-3:]
    return f"{i}.{d}"

ONES = "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen".split()
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
def words(n):
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")
    out = []
    for div, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand"), (100, "Hundred")):
        q, n = divmod(n, div)
        if q: out.append(words(q) + " " + name)
    if n: out.append(words(n))
    return " ".join(out)

def inr_words(t):
    t = round(float(t), 2); r = int(t); p = int(round((t - r) * 100))
    return "Indian Rupee " + words(r) + (f" and {words(p)} Paise" if p else "") + " Only"

class Panel(Flowable):
    """Rounded, optionally tinted box that holds other flowables."""
    def __init__(s, items, w, bg=None, stroke=None, r=3 * mm, pad=4 * mm):
        super().__init__(); s.items, s.w, s.bg, s.stroke, s.r, s.pad, s.min_h = items, w, bg, stroke, r, pad, 0
    def wrap(s, aw, ah):
        s.hs = [f.wrap(s.w - 2 * s.pad, 1e6)[1] for f in s.items]
        s.h = max(sum(s.hs) + 2 * s.pad, s.min_h)
        return s.w, s.h
    def draw(s):
        c = s.canv
        if s.bg or s.stroke:
            c.saveState()
            if s.bg: c.setFillColor(s.bg)
            if s.stroke: c.setStrokeColor(s.stroke); c.setLineWidth(.6)
            c.roundRect(0, 0, s.w, s.h, s.r, stroke=1 if s.stroke else 0, fill=1 if s.bg else 0); c.restoreState()
        y = s.h - s.pad
        for f, h in zip(s.items, s.hs):
            y -= h; f.drawOn(c, s.pad, y)

class RImg(Flowable):
    def __init__(s, data, w, h, r=3 * mm): super().__init__(); s.data, s.w, s.h, s.r = data, w, h, r
    def wrap(s, aw, ah): return s.w, s.h
    def draw(s):
        c = s.canv; c.saveState(); p = c.beginPath(); p.roundRect(0, 0, s.w, s.h, s.r); c.clipPath(p, stroke=0, fill=0)
        c.drawImage(ImageReader(io.BytesIO(s.data)), 0, 0, s.w, s.h); c.restoreState()

def fit(iid, mw, mh, r=3 * mm):
    b = img_get(iid) if iid else None
    if not b: return None
    try: w, h = ImageReader(io.BytesIO(b)).getSize()
    except Exception: return None
    k = min(mw / w, mh / h); return RImg(b, w * k, h * k, r)

def qr(c, data, x, y, size):
    w = QrCodeWidget(data); b = w.getBounds()
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0]); d.add(w)
    renderPDF.draw(d, c, x, y); c.linkURL(data, (x, y, x + size, y + size))

def make_pdf(iid):
    d = load_all()
    inv = next((i for i in d["inv"] if i["id"] == iid), None)
    if not inv: return None
    s = d["set"] or {}; cu = next((c for c in d["cust"] if c["name"] == inv.get("cname")), {})
    cur = s.get("cur", "₹"); f = lambda v: float(v or 0)
    sub = sum(f(t.get("qty")) * f(t.get("rate")) for t in inv["items"])
    x = max(0, sub - f(inv.get("disc"))); tax = x * f(inv.get("tax")) / 100; total = x + tax
    paid = inv.get("status") == "paid"; bal = 0 if paid else total
    dt = datetime.strptime(inv["date"], "%Y-%m-%d"); dmy = dt.strftime("%d %b %Y")
    no = "INV-%06d" % int(inv.get("no", 0)); W = 182 * mm

    # --- header
    lg = fit(s.get("logo"), 40 * mm, 26 * mm, 0)
    addr = "<br/>".join(X(l) for l in s.get("addr", "").split("\n") if l.strip())
    contact = X(" · ".join(v for v in (s.get("phone"), s.get("email")) if v))
    biz = [P(X(s.get("name", "")), "B", 15, color=MAROON, lead=19), Spacer(1, 2), P(addr, size=8.5, color=GREY)]
    if contact: biz += [Spacer(1, 2), P(contact, size=8.5, color=GREY)]
    right = [P(X(s.get("title", "TAX INVOICE")), "B", 19, 2, PINK, 23), Spacer(1, 4), P(no, "B", 11, 2, MAROON),
             P("PAID" if paid else "UNPAID", "B", 9, 2, GREEN if paid else AMBER)]
    head = Table([[lg or "", biz, right]], [42 * mm, 78 * mm, 62 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    flow = [head, HRFlowable(width="100%", thickness=1.4, color=PINK, spaceBefore=4 * mm, spaceAfter=5 * mm)]

    # --- billed to / details
    bill = [P("Billed to", size=8, color=GREY), Spacer(1, 2), P(X(inv.get("cname") or "Walk-in customer"), "B", 12, color=MAROON, lead=15)]
    for v in (cu.get("addr"), cu.get("phone")):
        if v: bill.append(P(X(v), size=8.5, color=GREY))
    rows = [("Invoice date", dmy), ("Terms", "Due on Receipt"), ("Due date", dmy)]
    det = Table([[P(a, size=8.5, color=GREY), P(X(b), "B", 9, 2, MAROON)] for a, b in rows], [28 * mm, 52 * mm])
    det.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    L, R = Panel(bill, 88 * mm, SOFT), Panel([P("Invoice details", size=8, color=GREY), Spacer(1, 3), det], 88 * mm, SOFT)
    L.min_h = R.min_h = max(L.wrap(0, 0)[1], R.wrap(0, 0)[1])
    pair = Table([[L, R]], [91 * mm, 91 * mm])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 3 * mm), ("LEFTPADDING", (1, 0), (1, 0), 3 * mm)]))
    flow.append(pair)
    if inv.get("subject"):
        flow += [Spacer(1, 3 * mm), Panel([P("Subject", size=8, color=GREY), Spacer(1, 2), P(X(inv["subject"]), size=10, color=MAROON)], W, stroke=LINE)]
    flow.append(Spacer(1, 6 * mm))

    # --- items
    W9 = colors.white
    data = [[P(h, "B", 8.5, a, W9) for h, a in (("#", 0), ("Description", 0), ("Qty", 2), ("Rate", 2), ("Amount", 2))]]
    for n, t in enumerate(inv["items"], 1):
        q, r = f(t.get("qty")), f(t.get("rate"))
        data.append([P(str(n), color=GREY), P(X(t.get("name", "")), "B", 9.5, color=MAROON), P(fmt(q), align=2), P(fmt(r), align=2), P(fmt(q * r), "B", 9, 2)])
    it = Table(data, [10 * mm, 96 * mm, 24 * mm, 24 * mm, 28 * mm], repeatRows=1)
    it.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MAROON), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW]), ("LINEBELOW", (0, 1), (-1, -1), .4, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    flow += [it, Spacer(1, 4 * mm)]

    # --- totals
    tr = [[P("Sub total", size=9, align=2, color=GREY), P(fmt(sub), size=9, align=2)]]
    if f(inv.get("disc")): tr.append([P("Discount", size=9, align=2, color=GREY), P("-" + fmt(inv["disc"]), size=9, align=2)])
    if f(inv.get("tax")): tr.append([P(f"Tax ({f(inv['tax']):g}%)", size=9, align=2, color=GREY), P(fmt(tax), size=9, align=2)])
    tr += [[P("Total", "B", 11, 2, W9), P(cur + fmt(total), "B", 11, 2, W9)], [P("Balance due", "B", 9.5, 2, MAROON), P(cur + fmt(bal), "B", 10.5, 2, MAROON)]]
    k = len(tr)
    tt = Table(tr, [32 * mm, 38 * mm]); tt.setStyle(TableStyle([("BACKGROUND", (0, k - 2), (-1, k - 2), PINK), ("BACKGROUND", (0, k - 1), (-1, k - 1), SOFT),
                            ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    words_ = [P("Total in words", size=8, color=GREY), Spacer(1, 2), P(X(inr_words(total)), "BI", 9, color=MAROON)]
    tot = Table([[words_, tt]], [108 * mm, 74 * mm]); tot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    flow.append(tot)

    # --- photos
    one = len(inv.get("imgs", [])) == 1
    pics = [p for p in (fit(i, 100 * mm if one else 86 * mm, 70 * mm) for i in inv.get("imgs", [])) if p]
    if pics:
        grid = [pics[i:i + 2] + [""] * (2 - len(pics[i:i + 2])) for i in range(0, len(pics), 2)] if not one else [[pics[0]]]
        g = Table(grid, [91 * mm, 91 * mm] if not one else [W]); g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))
        flow += [Spacer(1, 3 * mm), g]

    # --- page decoration: top bar + thank-you footer with QR codes
    ph = re.sub(r"\D", "", s.get("phone", "")); ph = "91" + ph if len(ph) == 10 else ph
    ig = s.get("insta", "").strip().lstrip("@")
    if "instagram.com/" in ig: ig = ig.split("instagram.com/")[1].split("/")[0].split("?")[0]
    qrs = ([("https://wa.me/" + ph, "WhatsApp")] if ph else []) + ([("https://instagram.com/" + ig, "Instagram")] if ig else [])
    msg = s.get("note") or "Thank you for choosing us. We hope to serve you again!"
    def deco(c, doc):
        c.saveState(); c.setFillColor(PINK); c.rect(0, PH - 4 * mm, PW, 4 * mm, fill=1, stroke=0)
        x0, y0, w, h = 14 * mm, 8 * mm, 182 * mm, 42 * mm
        c.setFillColor(SOFT); c.roundRect(x0, y0, w, h, 4 * mm, fill=1, stroke=0)
        qs, edge = 22 * mm, x0 + w - 6 * mm
        for k, (url, lab) in enumerate(reversed(qrs)):
            qx = edge - qs - k * (qs + 6 * mm)
            c.setFillColor(colors.white); c.roundRect(qx - 1.5 * mm, y0 + 8.5 * mm, qs + 3 * mm, qs + 3 * mm, 2 * mm, fill=1, stroke=0)
            qr(c, url, qx, y0 + 10 * mm, qs); c.setFont("R", 7); c.setFillColor(GREY); c.drawCentredString(qx + qs / 2, y0 + 4.5 * mm, lab)
        tw = (edge - len(qrs) * (qs + 6 * mm) - x0 - 7 * mm) if qrs else w - 14 * mm
        c.setFillColor(MAROON)
        if HAS_S: c.setFont("S", 27); c.drawString(x0 + 7 * mm, y0 + h - 13 * mm, "Thank you")
        else: c.setFont("BI", 18); c.drawString(x0 + 7 * mm, y0 + h - 12 * mm, "Thank you")
        small = len(msg) > 200
        p = P(X(msg), "I", 7.4 if small else 8.4, 0, MAROON, 9.4 if small else 10.8); _, phh = p.wrap(tw, 100 * mm)
        p.drawOn(c, x0 + 7 * mm, y0 + h - 16 * mm - phh)
        line = "   ·   ".join(v for v in (("Feedback & orders: " + s["phone"]) if s.get("phone") else "", ("@" + ig) if ig else "") if v)
        c.setFont("R", 8); c.setFillColor(GREY); c.drawString(x0 + 7 * mm, y0 + 10.5 * mm, line)
        if s.get("sign"): c.setFont("B", 9.5); c.setFillColor(PINK); c.drawString(x0 + 7 * mm, y0 + 5 * mm, s["sign"])
        c.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=no, author=s.get("name", ""))
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(14 * mm, 54 * mm, 182 * mm, PH - 66 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=deco)])
    doc.build(flow)
    return buf.getvalue(), no
