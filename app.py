
import streamlit as st
import pandas as pd
import io, uuid, os
import textwrap
from pathlib import Path
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.graphics.barcode import qr
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------- Fonts for PDF ----------------
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    FONT_REG = "DejaVuSans"
    FONT_BLD = "DejaVuSans-Bold"
except Exception:
    FONT_REG = "Helvetica"
    FONT_BLD = "Helvetica-Bold"

st.set_page_config(page_title="Παραγγελίες Μαθητών", layout="wide")

# ---------------- Paths & Config ----------------
DATA_DIR = Path(".")
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
ORDERS_PATH   = DATA_DIR / "orders.csv"
DEFAULT_LOGO  = Path("/mnt/data/logo (2).png")
APP_URL = st.secrets.get("APP_URL", os.getenv("APP_URL", "https://your-app-url-here"))
ADMIN_PIN = st.secrets.get("ADMIN_PIN", os.getenv("ADMIN_PIN", "1234"))
APP_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", ""))

# ---------------- Role ----------------
role = st.sidebar.selectbox("Ρόλος", ["Καταχώριση", "Διαχειριστής"], index=0)
is_admin = False
if role == "Διαχειριστής":
    pin = st.sidebar.text_input("PIN Διαχειριστή", type="password")
    if pin == str(ADMIN_PIN):
        is_admin = True
        st.sidebar.success("✅ Διαχειριστής/ρια")
    else:
        st.sidebar.warning("Πληκτρολόγησε σωστό PIN για λειτουργίες διαχείρισης.")

# ---------------- Logo controls ----------------
st.sidebar.markdown("### Ρυθμίσεις εμφάνισης")
if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = DEFAULT_LOGO.read_bytes() if DEFAULT_LOGO.exists() else None

if is_admin:
    st.sidebar.markdown("#### Λογότυπο & URL για QR")
    logo_file = st.sidebar.file_uploader("Ανέβασμα λογοτύπου (PNG/JPG)", type=["png","jpg","jpeg"])
    if logo_file is not None:
        st.session_state["logo_bytes"] = logo_file.read()
    app_url = st.sidebar.text_input("URL εφαρμογής (για QR)", APP_URL)
    if st.session_state.get("logo_bytes"):
        st.sidebar.image(st.session_state["logo_bytes"], caption="Λογότυπο", use_column_width=True)
else:
    app_url = APP_URL

# ---------------- Diagnostics (sidebar) ----------------
with st.sidebar.expander("🔍 Διαγνωστικά"):
    try:
        for lbl, path in [("products.csv", PRODUCTS_PATH), ("students.csv", STUDENTS_PATH), ("orders.csv", ORDERS_PATH)]:
            ok = path.exists()
            size = (path.stat().st_size if ok else 0)
            st.write(f"- {lbl}: {'✅' if ok else '❌'} ({size} bytes)")
        _p = pd.read_csv(PRODUCTS_PATH) if PRODUCTS_PATH.exists() else pd.DataFrame()
        _s = pd.read_csv(STUDENTS_PATH) if STUDENTS_PATH.exists() else pd.DataFrame()
        _o = pd.read_csv(ORDERS_PATH) if ORDERS_PATH.exists() else pd.DataFrame()
        st.write(f"Προϊόντα: {len(_p)} • Μαθητές/τριες: {len(_s)} • Γραμμές παραγγελιών: {len(_o)}")
        st.write("Ρόλος:", role, "| Admin:", is_admin)
    except Exception as e:
        st.write("Σφάλμα:", e)


# ---------------- Login (optional) ----------------
# Αν οριστεί APP_PASSWORD (στο Secrets ή env), η εφαρμογή ζητά κωδικό στην είσοδο.
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if APP_PASSWORD and not st.session_state["logged_in"]:
    # Εμφάνιση απλού header
    st.markdown("## 🍔 Παραγγελίες Μαθητών")
    st.info("🔐 Η πρόσβαση στην εφαρμογή προστατεύεται με κωδικό.")
    pwd = st.text_input("Κωδικός πρόσβασης", type="password")
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Είσοδος"):
            if str(pwd) == str(APP_PASSWORD):
                st.session_state["logged_in"] = True
                st.success("✅ Επιτυχής είσοδος")
                st.rerun()
            else:
                st.error("Λάθος κωδικός.")
    with c2:
        st.caption("Ο κωδικός ορίζεται ως APP_PASSWORD στο Streamlit Secrets (TOML) ή ως environment variable.")
    st.stop()

def show_topbar():
    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        if st.session_state.get("logo_bytes"):
            st.image(st.session_state["logo_bytes"], width=64)
    with col_title:
        st.markdown("## 🍔 Παραγγελίες Μαθητών")
        st.caption("Μαθητές από πολλά σχολεία, παραγγελίες, PDF δελτία, αναφορές & εξαγωγές.")

# ---------------- Loaders / Savers ----------------
@st.cache_data
def load_products():
    if PRODUCTS_PATH.exists():
        df = pd.read_csv(PRODUCTS_PATH)
    else:
        df = pd.DataFrame(columns=["product","price"])
    if "product" not in df.columns: df["product"] = ""
    if "price" not in df.columns: df["price"] = 0.0
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    return df

@st.cache_data
def load_students():
    if STUDENTS_PATH.exists():
        df = pd.read_csv(STUDENTS_PATH)
    else:
        df = pd.DataFrame(columns=["student","school","class"])
    for c in ["student","school","class"]:
        if c not in df.columns: df[c] = ""
    df["student"] = df["student"].astype(str).str.strip()
    df["school"]  = df["school"].astype(str).str.strip()
    df["class"]   = df["class"].astype(str).str.strip()
    return df

@st.cache_data
def load_orders():
    if ORDERS_PATH.exists():
        df = pd.read_csv(ORDERS_PATH, parse_dates=["date"])
    else:
        df = pd.DataFrame(columns=["order_id","date","student","school","class","product","qty","unit_price","total"])
    for c in ["order_id","date","student","school","class","product","qty","unit_price","total"]:
        if c not in df.columns: df[c] = pd.NA
    df["order_id"] = df["order_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["student"] = df["student"].astype(str).str.strip()
    df["school"]  = df["school"].astype(str).str.strip()
    df["class"]   = df["class"].astype(str).str.strip()
    df["product"] = df["product"].astype(str).str.strip()
    for c in ["qty","unit_price","total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df

def save_products(df):
    df = df[["product","price"]].copy()
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df.drop_duplicates(subset=["product"]).sort_values("product")
    df.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    (load_products.clear() if hasattr(load_products, "clear") else None)

def save_students(df):
    for c in ["student","school","class"]:
        if c not in df.columns: df[c] = ""
    df = df[["student","school","class"]].copy()
    df["student"] = df["student"].astype(str).str.strip()
    df["school"]  = df["school"].astype(str).str.strip()
    df["class"]   = df["class"].astype(str).str.strip()
    df = df[df["student"].str.len()>0].drop_duplicates(subset=["student","school","class"]).sort_values(["school","class","student"])
    df.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    (load_students.clear() if hasattr(load_students, "clear") else None)

def save_orders(df):
    cols = ["order_id","date","student","school","class","product","qty","unit_price","total"]
    for c in cols:
        if c not in df.columns: df[c] = pd.NA
    df = df[cols].copy()
    df.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    (load_orders.clear() if hasattr(load_orders, "clear") else None)

# ---------------- PDF helpers ----------------
def _draw_header_with_logo(c, title):
    width, height = A4
    left = 2*cm
    right = width - 2*cm
    top = height - 2*cm
    if st.session_state.get("logo_bytes"):
        try:
            img = ImageReader(io.BytesIO(st.session_state["logo_bytes"]))
            c.drawImage(img, left, top-1.2*cm, width=1.2*cm, height=1.2*cm, preserveAspectRatio=True, mask='auto')
            title_x = left + 1.4*cm
        except Exception:
            title_x = left
    else:
        title_x = left
    c.setFont(FONT_BLD, 14)
    c.drawString(title_x, top, title)
    c.setFont(FONT_REG, 9)
    c.drawRightString(right, top, f"Ημερομηνία εξαγωγής: {pd.Timestamp.today().date()}")
    return top - 0.8*cm

def _draw_footer(c, page_num, app_url):
    width, _ = A4
    left = 2*cm
    right = width - 2*cm
    bottom = 1.5*cm
    c.setFont(FONT_REG, 8)
    c.drawString(left, bottom, f"Σελίδα {page_num}")
    c.drawRightString(right, bottom, f"Εκτύπωση: {pd.Timestamp.today().strftime('%Y-%m-%d %H:%M')}")
    if app_url and isinstance(app_url, str) and app_url.strip():
        try:
            q = qr.QrCode(app_url.strip(), barLevel='M')
            q.drawOn(c, right-2.2*cm, bottom-1.8*cm)
        except Exception:
            pass

def _paginate_new_page(c, title, app_url):
    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    return _draw_header_with_logo(c, title)


def pdf_by_student_summary(by_student: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    """
    Ειδικό PDF για «Ανά μαθητή/-τρια» με σταθερές στήλες/στοίχιση και 2 γραμμές στο ονοματεπώνυμο.
    Αποφεύγουμε επικαλύψεις με το σχολείο/τάξη.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)

    # Σταθερές θέσεις στηλών
    x_student = left
    x_school  = left + 7.0 * cm
    x_class   = left + 12.2 * cm
    x_qty_r   = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def draw_head(ypos: float) -> float:
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_student, ypos, "Μαθητής/-τρια")
        c.drawString(x_school,  ypos, "Σχολείο")
        c.drawString(x_class,   ypos, "Τάξη")
        c.drawRightString(x_qty_r,   ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = draw_head(y)

    for _, r in by_student.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = draw_head(y)

        student = wrap2(r.get("Μαθητής/-τρια", ""), width=24)  # έως 2 γραμμές
        school  = str(r.get("Σχολείο", "") or "")
        clazz   = str(r.get("Τάξη", "") or "")
        qty     = int(float(r.get("ποσότητα", 0) or 0))
        total   = float(r.get("σύνολο", 0.0) or 0.0)

        s1, s2 = (student.split("\n") + [""])[:2]

        # 1η γραμμή
        c.drawString(x_student, y, s1[:30])
        c.drawString(x_school,  y, school[:24])
        c.drawString(x_class,   y, clazz[:10])
        c.drawRightString(x_qty_r,   y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

        # 2η γραμμή ονοματεπωνύμου (αν υπάρχει)
        if s2.strip():
            if y < 2.4 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)
                y = draw_head(y)
            c.drawString(x_student, y, s2[:30])
            y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_class_summary(by_class: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    """Σταθερό layout για «Ανά τάξη»."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_school = left
    x_class  = left + 9.0 * cm
    x_qty_r  = right - 4.0 * cm
    x_total_r= right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_school, ypos, "Σχολείο")
        c.drawString(x_class,  ypos, "Τάξη")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)
    for _, r in by_class.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = head(y)
        school = str(r.get("Σχολείο","") or "")
        clazz  = str(r.get("Τάξη","") or "")
        qty    = int(float(r.get("ποσότητα",0) or 0))
        total  = float(r.get("σύνολο",0.0) or 0.0)
        c.drawString(x_school, y, school[:40])
        c.drawString(x_class,  y, clazz[:18])
        c.drawRightString(x_qty_r,   y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_school_summary(by_school: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    """Σταθερό layout για «Ανά σχολείο»."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_school = left
    x_qty_r  = right - 4.0 * cm
    x_total_r= right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_school, ypos, "Σχολείο")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)
    for _, r in by_school.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = head(y)
        school = str(r.get("Σχολείο","") or "")
        qty    = int(float(r.get("ποσότητα",0) or 0))
        total  = float(r.get("σύνολο",0.0) or 0.0)
        c.drawString(x_school, y, school[:55])
        c.drawRightString(x_qty_r,   y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_product_summary(by_product_df: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    """Σταθερό layout για «Ανά προϊόν» (προς κατάστημα). Περιμένει στήλες product, qty, total."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_product = left
    x_qty_r   = right - 3.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_product, ypos, "Προϊόν")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)
    for _, r in by_product_df.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = head(y)
        prod = str(r.get("product","") or "")
        qty  = int(float(r.get("qty",0) or 0))
        tot  = float(r.get("total",0.0) or 0.0)
        c.drawString(x_product, y, prod[:60])
        c.drawRightString(x_qty_r,   y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{tot:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

def pdf_grouped_by_school_student(df, title="Δελτίο"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 2*cm
    right = width - 2*cm

    y = _draw_header_with_logo(c, title)
    grand_total = 0.0

    for school, g1 in df.groupby("school"):
        if y < 3*cm: y = _paginate_new_page(c, title, app_url)
        c.setFont(FONT_BLD, 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.6*cm

        school_total = 0.0
        for student, g2 in g1.groupby("student"):
            if y < 3*cm: y = _paginate_new_page(c, title, app_url)
            c.setFont(FONT_BLD, 11)
            cls = (g2["class"].iloc[0] or "").strip()
            suffix = f" — Τάξη: {cls}" if cls else ""
            c.drawString(left, y, f"Μαθητής/-τρια: {student}{suffix}")
            y -= 0.5*cm

            c.setFont(FONT_BLD, 9)
            c.drawString(left, y, "Προϊόν")
            c.drawRightString(right-6.5*cm, y, "Τιμή (€)")
            c.drawRightString(right-3.5*cm, y, "Ποσότητα")
            c.drawRightString(right-0.5*cm, y, "Σύνολο (€)")
            y -= 0.4*cm
            c.setFont(FONT_REG, 9)

            subtotal = 0.0
            for _, row in g2.sort_values(["product"]).iterrows():
                if y < 2*cm: y = _paginate_new_page(c, title, app_url)
                c.drawString(left, y, str(row["product"]))
                c.drawRightString(right-6.5*cm, y, f"{float(row['unit_price'] or 0):.2f}")
                c.drawRightString(right-3.5*cm, y, f"{int(row['qty']) if pd.notna(row['qty']) else ''}")
                c.drawRightString(right-0.5*cm, y, f"{float(row['total'] or 0):.2f}")
                y -= 0.35*cm
                subtotal += float(row.get("total", 0) or 0)

            if y < 2*cm: y = _paginate_new_page(c, title, app_url)
            c.setFont(FONT_BLD, 10)
            c.drawRightString(right-0.5*cm, y, f"Σύνολο {student}: {subtotal:.2f} €")
            y -= 0.35*cm
            c.setLineWidth(0.5)
            c.line(left, y, right, y)
            y -= 0.45*cm
            c.setFont(FONT_REG, 9)
            school_total += subtotal

        if y < 2*cm: y = _paginate_new_page(c, title, app_url)
        c.setFont(FONT_BLD, 11)
        c.drawRightString(right-0.5*cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.7*cm
        grand_total += school_total

    if y < 2*cm: y = _paginate_new_page(c, title, app_url)
    c.setFont(FONT_BLD, 12)
    c.drawRightString(right-0.5*cm, y, f"Γενικό Σύνολο: {grand_total:.2f} €")

    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def pdf_products_report(df, title="Παραγγελία προς κατάστημα"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 2*cm
    right = width - 2*cm

    y = _draw_header_with_logo(c, title)
    c.setFont(FONT_BLD, 10)
    c.drawString(left, y, "Προϊόν")
    c.drawRightString(right-3*cm, y, "Σύνολο Ποσότητας")
    c.drawRightString(right-0.5*cm, y, "Σύνολο (€)")
    y -= 0.5*cm

    c.setFont(FONT_REG, 10)
    for _, row in df.iterrows():
        if y < 2*cm: y = _paginate_new_page(c, title, app_url)
        c.drawString(left, y, str(row["product"]))
        c.drawRightString(right-3*cm, y, f"{int(row['qty'])}")
        c.drawRightString(right-0.5*cm, y, f"{float(row['total']):.2f}")
        y -= 0.4*cm

    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def _wrap2(text, width=26, max_lines=2):
    try:
        s = "" if text is None else str(text)
    except Exception:
        s = f"{text}"
    parts = []
    for seg in s.split("\n"):
        parts.extend(textwrap.wrap(seg, width=width) or [""])
    parts = parts[:max_lines]
    return "\n".join(parts) if parts else ""

def pdf_table(df, title="Αναφορά", columns=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 2*cm
    right = width - 2*cm

    y = _draw_header_with_logo(c, title)
    cols = columns or [(col, col, "L") for col in df.columns]
    c.setFont(FONT_BLD, 9)
    step = (right-left) / max(1, len(cols))
    for i, (_c, head, _a) in enumerate(cols):
        c.drawString(left + i*step, y, str(head)[:22])
    y -= 0.45*cm
    c.setFont(FONT_REG, 9)

    for _, row in df.iterrows():
        if y < 2*cm:
            y = _paginate_new_page(c, title, app_url)
            c.setFont(FONT_BLD, 9)
            for i, (_c, head, _a) in enumerate(cols):
                c.drawString(left + i*step, y, str(head)[:22])
            y -= 0.45*cm
            c.setFont(FONT_REG, 9)
        for i, (col_key, _head, align) in enumerate(cols):
            val = row[col_key]
            if isinstance(val, (float, int)) and ("σύνολο" in _head.lower()):
                s = f"{float(val):.2f}"
            else:
                s = f"{val}"
            if "\n" in s:
                lines2 = s.split("\n")
                if align == "R":
                    c.drawRightString(left + (i+1)*step - 2, y, lines2[0][:22])
                else:
                    c.drawString(left + i*step, y, lines2[0][:26])
                y2 = y - 0.32*cm
                if len(lines2) > 1:
                    if align == "R":
                        c.drawRightString(left + (i+1)*step - 2, y2, lines2[1][:22])
                    else:
                        c.drawString(left + i*step, y2, lines2[1][:26])
            else:
                if align == "R":
                    c.drawRightString(left + (i+1)*step - 2, y, s[:22])
                else:
                    c.drawString(left + i*step, y, s[:26])
        y -= 0.60*cm if ("\n" in s) else 0.38*cm

    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ---------------- UI ----------------
show_topbar()

pages = ["Κατάλογος", "Μαθητές", "Παραγγελίες", "Σύνοψη", "Δελτία"]
if not is_admin:
    pages = ["Παραγγελίες", "Σύνοψη", "Δελτία"]
page = st.sidebar.radio("Μενού", pages, index=0)

# ---------------- Κατάλογος ----------------
if page == "Κατάλογος":
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()
    st.subheader("Τιμοκατάλογος")
    products = load_products().copy()

    with st.form("add_product"):
        c1, c2 = st.columns([3,1])
        with c1:
            p = st.text_input("Προϊόν", placeholder="π.χ. Club sandwich")
        with c2:
            pr = st.number_input("Τιμή", min_value=0.0, step=0.1, format="%.2f")
        submitted = st.form_submit_button("➕ Προσθήκη")
    if submitted and p.strip():
        if (products["product"].str.lower() == p.strip().lower()).any():
            st.warning("Υπάρχει ήδη προϊόν με αυτό το όνομα.")
        else:
            products.loc[len(products)] = [p.strip(), pr]
            save_products(products)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("**Ανέβασμα Excel προϊόντων (Προϊόν – Τιμή)**")
    replace_products = st.checkbox("✅ Αντικατάσταση όλων των υπαρχόντων προϊόντων", key="replace_products")
    uplp = st.file_uploader("Επιλογή αρχείου Excel προϊόντων", type=["xlsx"])
    if uplp is not None:
        try:
            xl = pd.ExcelFile(uplp)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                headers = {str(c).strip().lower(): c for c in df.columns}
                if "προϊόν" in headers and "τιμή" in headers:
                    tmp = df.rename(columns={headers["προϊόν"]:"product", headers["τιμή"]:"price"})[["product","price"]]
                elif "product" in headers and "price" in headers:
                    tmp = df.rename(columns={headers["product"]:"product", headers["price"]:"price"})[["product","price"]]
                else:
                    tmp = df.iloc[:, :2].copy()
                    tmp.columns = ["product","price"]
                frames.append(tmp)
            merged = pd.concat(frames, ignore_index=True)[["product","price"]]
            if replace_products:
                save_products(merged)
                st.success("Έγινε αντικατάσταση όλων των προϊόντων από το Excel.")
            else:
                save_products(pd.concat([products, merged], ignore_index=True))
                st.success("Ο τιμοκατάλογος ενημερώθηκε από το Excel (συγχώνευση).")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    st.markdown("#### Διαγραφές")
    if not products.empty:
        to_delete = st.selectbox("Διαγραφή μεμονωμένου προϊόντος", products["product"].tolist(), key="del_prod_single")
        confirm = st.checkbox("✅ Επιβεβαίωση", key="confirm_prod_single")
        if st.button("🗑️ Διαγραφή") and confirm:
            products = products[products["product"] != to_delete].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκε: {to_delete}")
            st.rerun()

    # Μαζική διαγραφή προϊόντων
    st.markdown("#### Μαζική διαγραφή προϊόντων")
    multi_del = st.multiselect("Επέλεξε προϊόντα", products["product"].tolist(), key="del_prod_multi")
    confirm_multi = st.checkbox("✅ Επιβεβαίωση μαζικής", key="confirm_prod_multi")
    if st.button("🗑️ Διαγραφή επιλεγμένων") and multi_del and confirm_multi:
        products = products[~products["product"].isin(multi_del)].reset_index(drop=True)
        save_products(products)
        st.success(f"Διαγράφηκαν: {', '.join(multi_del)}")
        st.rerun()

    st.markdown("#### Λίστα προϊόντων")
    st.dataframe(products.rename(columns={"product":"Προϊόν","price":"Τιμή (€)"}), use_container_width=True)

# ---------------- Μαθητές ----------------
elif page == "Μαθητές":
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()
    st.subheader("Διαχείριση Μαθητών, Σχολείων & Τάξης")
    students = load_students().copy()

    with st.form("add_student"):
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            s = st.text_input("Ονοματεπώνυμο")
        with c2:
            sch = st.text_input("Σχολείο", placeholder="π.χ. 1ο Γυμνάσιο")
        with c3:
            cl = st.text_input("Τάξη", placeholder="π.χ. Β1, Γ2...")
        submitted = st.form_submit_button("➕ Προσθήκη")
    if submitted and s.strip():
        exists = ((students["student"].str.lower()==s.strip().lower()) &
                  (students["school"].str.lower()==sch.strip().lower()) &
                  (students["class"].str.lower()==cl.strip().lower())).any()
        if exists:
            st.warning("Υπάρχει ήδη.")
        else:
            students.loc[len(students)] = [s.strip(), sch.strip(), cl.strip()]
            save_students(students)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("**Ανέβασμα Excel: Ονοματεπώνυμο – Σχολείο – Τάξη**")
    replace_students = st.checkbox("✅ Αντικατάσταση όλων των υπαρχόντων μαθητών/τριών", key="replace_students")
    upl = st.file_uploader("Επιλογή αρχείου Excel", type=["xlsx"])
    if upl is not None:
        try:
            xl = pd.ExcelFile(upl)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                cols = {str(c).strip().lower(): c for c in df.columns}
                if "ονοματεπώνυμο" in cols:
                    if "σχολείο" not in cols: df["σχολείο"] = ""
                    if "τάξη" not in cols: df["τάξη"] = ""
                    tmp = df.rename(columns={"ονοματεπώνυμο":"student","σχολείο":"school","τάξη":"class"})[["student","school","class"]]
                elif "student" in cols:
                    if "school" not in cols: df["school"] = ""
                    if "class"  not in cols: df["class"]  = ""
                    tmp = df.rename(columns={"student":"student","school":"school","class":"class"})[["student","school","class"]]
                else:
                    tmp = df.copy()
                    if tmp.shape[1] >= 3:
                        tmp = tmp.iloc[:, :3]
                        tmp.columns = ["student","school","class"]
                    elif tmp.shape[1] == 2:
                        tmp.columns = ["student","school"]
                        tmp["class"] = ""
                    else:
                        tmp.columns = ["student"]
                        tmp["school"] = ""
                        tmp["class"] = ""
                frames.append(tmp[["student","school","class"]])
            merged = pd.concat(frames, ignore_index=True)[["student","school","class"]]
            if replace_students:
                save_students(merged)
                st.success("Έγινε αντικατάσταση όλων των μαθητών/τριών από το Excel.")
            else:
                save_students(pd.concat([students, merged], ignore_index=True))
                st.success("Οι μαθητές ενημερώθηκαν από το Excel (συγχώνευση).")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    st.markdown("#### Διαγραφές")
    if not students.empty:
        students = load_students().copy()
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
        sel = st.selectbox("Διαγραφή μεμονωμένου/ης", students["label"].tolist(), key="del_student_single")
        confirm = st.checkbox("✅ Επιβεβαίωση", key="confirm_st_single")
        if st.button("🗑️ Διαγραφή") and confirm:
            idx = students.index[students["label"]==sel][0]
            name_del = students.loc[idx, "label"]
            students = students.drop(index=idx).drop(columns=["label"]).reset_index(drop=True)
            save_students(students)
            st.success(f"Διαγράφηκε: {name_del}")
            st.rerun()

    # Μαζική διαγραφή μαθητών/τριών
    st.markdown("#### Μαζική διαγραφή μαθητών/τριών")
    students_all = load_students().copy()
    students_all["label"] = students_all.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
    to_multi = st.multiselect("Επέλεξε από τη λίστα", students_all["label"].tolist(), key="del_student_multi")
    confirm_multi = st.checkbox("✅ Επιβεβαίωση μαζικής", key="confirm_st_multi")
    if st.button("🗑️ Διαγραφή επιλεγμένων μαθητών/τριών") and to_multi and confirm_multi:
        keep = ~students_all["label"].isin(to_multi)
        kept = students_all.loc[keep, ["student","school","class"]].reset_index(drop=True)
        save_students(kept)
        st.success(f"Διαγράφηκαν: {len(to_multi)} εγγραφές")
        st.rerun()

    st.markdown("#### Τρέχουσα λίστα")
    st.dataframe(load_students().rename(columns={"student":"Ονοματεπώνυμο","school":"Σχολείο","class":"Τάξη"}), use_container_width=True)

# ---------------- Παραγγελίες ----------------
elif page == "Παραγγελίες":
    products = load_products()
    students = load_students()
    orders = load_orders().copy()

    tabs = st.tabs(["🆕 Νέα παραγγελία", "✏️ Διόρθωση / Διαγραφή"])

    # ---- Νέα παραγγελία
    with tabs[0]:
        st.subheader("Καταχώριση")
        st.caption(f"📦 Προϊόντα: {len(products)} • 👩‍🎓 Μαθητές: {len(students)}")
        if students.empty or products.empty:
            st.info("Πρέπει να υπάρχουν μαθητές/τριες και προϊόντα. Συμπλήρωσέ τα από τα μενού ‘Κατάλογος’ και ‘Μαθητές’.")
        else:
            
            # Τρόπος ταξινόμησης μαθητών/τριών στην καταχώριση
            sort_mode = st.radio(
                "Ταξινόμηση μαθητών/τριών",
                ["Αλφαβητικά", "Ανά σχολείο → τάξη → αλφαβητικά", "Ανά τάξη → αλφαβητικά"],
                horizontal=True,
                index=1,
                key="sort_mode_entry"
            )
students = students.copy()
            students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
            c1, c2 = st.columns([1.2,3])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today(), key="order_date")
            with c2:
                            if sort_mode == "Αλφαβητικά":
                students = students.sort_values(["student","school","class"], na_position="last")
            elif sort_mode == "Ανά τάξη → αλφαβητικά":
                students = students.sort_values(["class","student","school"], na_position="last")
            else:
                students = students.sort_values(["school","class","student"], na_position="last")
            label = st.selectbox("Μαθητής/-τρια", students["label"].tolist(), key="order_student")

            # reset default rows when student changes
            if "last_student_label" not in st.session_state:
                st.session_state["last_student_label"] = None
            if st.session_state["last_student_label"] != label:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": ["", "", ""], "Ποσότητα": [1, 1, 1], "Μερικό (€)": [0.0,0.0,0.0]})
                st.session_state["last_student_label"] = label

            catalog = products["product"].tolist()
            if "order_editor_df" not in st.session_state:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
            with st.form("order_form", clear_on_submit=False):
                    edited = st.data_editor(
                    st.session_state["order_editor_df"],
                    key="order_editor",
                    num_rows="dynamic",
                    column_config={
                        "Προϊόν": st.column_config.SelectboxColumn(
                            "Προϊόν",
                            options=catalog,
                            required=False,
                            help="Επιλογή προϊόντος"
                        ),
                        "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1, help="Τουλάχιστον 1"),
                        "Μερικό (€)": st.column_config.NumberColumn("Μερικό (€)", format="%.2f", disabled=True, help="Τιμή × Ποσότητα")
                    },
                    use_container_width=True
                )
                # sync & recompute line totals
                try:
                    edited = edited.rename(columns={c:str(c) for c in edited.columns})
                    if "Ποσότητα" in edited.columns:
                        edited["Ποσότητα"] = pd.to_numeric(edited["Ποσότητα"], errors="coerce").fillna(1).astype(int)
                    if "Προϊόν" in edited.columns:
                        edited["Προϊόν"] = edited["Προϊόν"].astype(str)
                    price_map = dict(zip(products["product"], products["price"]))
                    def _line_total(r):
                        p = str(r.get("Προϊόν",""))
                        q = int(r.get("Ποσότητα", 1)) if pd.notna(r.get("Ποσότητα", 1)) else 1
                        pr = float(price_map.get(p, 0.0))
                        return pr * q
                    edited["Μερικό (€)"] = edited.apply(_line_total, axis=1)
                except Exception:
                    pass
                st.session_state["order_editor_df"] = edited

                # identify student pieces
                row = students.loc[students["label"]==label].iloc[0]
                s, sch, cl = row["student"], row["school"], row["class"]

                # subtotals
                editor_df = st.session_state.get("order_editor_df", pd.DataFrame())
                subtotal = float(editor_df.get("Μερικό (€)", pd.Series(dtype=float)).sum()) if "Μερικό (€)" in editor_df.columns else 0.0
                st.markdown(f"**Σύνολο τρέχουσας παραγγελίας:** {subtotal:.2f} €")

                today_total = orders[(orders["student"]==s) & (orders["date"].dt.date==d)].total.sum() if not orders.empty else 0.0
                st.caption(f"Σύνολο μαθητή για την {d}: {float(today_total):.2f} €")

                # buttons
                cbtn1, cbtn2, cbtn3 = st.columns([1,1,2])
                with cbtn1:
                    save_click = st.form_submit_button("✅ Καταχώριση παραγγελίας")
                with cbtn2:
                    clear_click = st.form_submit_button("🧹 Νέα παραγγελία")
                with cbtn3:
                    add_row = st.form_submit_button("➕ Προσθήκη γραμμής")

            # (τέλος φόρμας καταχώρισης)
            if save_click:
                new_rows = []
                new_ids = []
                editor_df = st.session_state.get("order_editor_df", pd.DataFrame({"Προϊόν": [], "Ποσότητα": []})).copy()
                for _, r in editor_df.iterrows():
                    p = str(r.get("Προϊόν", "")).strip()
                    if not p or p not in catalog:
                        continue
                    qty = int(r.get("Ποσότητα", 1)) if pd.notna(r.get("Ποσότητα", 1)) else 1
                    unit_price = float(products.loc[products["product"]==p, "price"].iloc[0]) if (products["product"]==p).any() else 0.0
                    oid = str(uuid.uuid4())
                    total = unit_price * qty
                    new_rows.append({
                        "order_id": oid,
                        "date": pd.to_datetime(d),
                        "student": s,
                        "school": sch,
                        "class": cl,
                        "product": p,
                        "qty": qty,
                        "unit_price": unit_price,
                        "total": total
                    })
                    new_ids.append(oid)
                # if no product rows, store a placeholder header row
                if not new_rows:
                    oid = str(uuid.uuid4())
                    new_rows = [{
                        "order_id": oid,
                        "date": pd.to_datetime(d),
                        "student": s,
                        "school": sch,
                        "class": cl,
                        "product": "(χωρίς προϊόν)",
                        "qty": 0,
                        "unit_price": 0.0,
                        "total": 0.0
                    }]
                    new_ids = [oid]

                orders_latest = load_orders().copy()
                orders_latest = pd.concat([orders_latest, pd.DataFrame(new_rows)], ignore_index=True)
                save_orders(orders_latest)
                st.session_state.setdefault("my_last_orders", [])
                st.session_state["my_last_orders"].extend(new_ids)
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
                st.success("Η παραγγελία αποθηκεύτηκε.")
                st.rerun()

            if clear_click:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
                st.rerun()

            if add_row:
                df_tmp = st.session_state.get("order_editor_df", pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})).copy()
                df_tmp = pd.concat([df_tmp, pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})], ignore_index=True)
                st.session_state["order_editor_df"] = df_tmp
                st.rerun()

    # ---- Διόρθωση / Διαγραφή
    with tabs[1]:
        st.subheader("Διόρθωση / Διαγραφή")
        st.caption(f"📦 Προϊόντα: {len(load_products())} • 👩‍🎓 Μαθητές: {len(load_students())}")
        products = load_products()
        students = load_students()
        orders = load_orders().copy()

        if not is_admin:
            only_mine = st.checkbox("Εμφάνιση μόνο των δικών μου καταχωρίσεων (συνεδρία)", value=True)
            if only_mine:
                ids = st.session_state.get("my_last_orders", [])
                orders = orders[orders["order_id"].isin(ids)].copy()

        c1, c2, c3 = st.columns(3)
        with c1:
            f_student = st.multiselect("Μαθητές/-τριες", sorted(orders["student"].dropna().unique().tolist()))
        with c2:
            f_school = st.multiselect("Σχολεία", sorted(orders["school"].dropna().unique().tolist()))
        with c3:
            f_class = st.multiselect("Τάξεις", sorted(orders["class"].dropna().unique().tolist()))

        df = orders.copy()
        if f_student: df = df[df["student"].isin(f_student)]
        if f_school:  df = df[df["school"].isin(f_school)]
        if f_class:   df = df[df["class"].isin(f_class)]

        if df.empty:
            st.info("Δεν βρέθηκαν γραμμές.")
        else:

            st.markdown("#### Προβολή ανά μαθητή/-τρια (όλα τα είδη μαζί)")
            stus = sorted(df["student"].dropna().unique().tolist())
            sel_student_all = st.selectbox("Μαθητής/-τρια", ["(επιλογή...)"] + stus, key="edit_student_all")
            if sel_student_all != "(επιλογή...)":
                df_s = df[df["student"] == sel_student_all].copy().sort_values(["date","product"])
                view_cols = ["date","school","class","product","qty","unit_price","total","order_id"]
                for c in view_cols:
                    if c not in df_s.columns:
                        df_s[c] = pd.NA
                df_s["date"] = pd.to_datetime(df_s["date"], errors="coerce")
                df_s["Σύνολο (€)"] = df_s["total"].astype(float)

                df_s_view = df_s.rename(columns={
                    "date":"Ημερομηνία","school":"Σχολείο","class":"Τάξη",
                    "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)"
                })[["Ημερομηνία","Σχολείο","Τάξη","Προϊόν","Ποσότητα","Τιμή (€)","Σύνολο (€)","order_id"]]

                st.markdown(f"**Σύνολο μαθητή/-τριας:** {float(df_s['total'].sum()):.2f} €")

                edited_all = st.data_editor(
                    df_s_view.drop(columns=["order_id"]),
                    key="edit_all_editor",
                    num_rows="fixed",
                    column_config={
                        "Ημερομηνία": st.column_config.DateColumn("Ημερομηνία"),
                        "Προϊόν": st.column_config.SelectboxColumn("Προϊόν", options=products["product"].tolist()),
                        "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1),
                        "Τιμή (€)": st.column_config.NumberColumn("Τιμή (€)", min_value=0.0, step=0.1, format="%.2f"),
                        "Σύνολο (€)": st.column_config.NumberColumn("Σύνολο (€)", disabled=True, format="%.2f"),
                    },
                    use_container_width=True
                )

                csave, cdel = st.columns([1,1])
                with csave:
                    if st.button("💾 Αποθήκευση αλλαγών (όλες οι γραμμές)"):
                        try:
                            edited_all = edited_all.copy()
                            edited_all["Ποσότητα"] = pd.to_numeric(edited_all["Ποσότητα"], errors="coerce").fillna(1).astype(int)
                            edited_all["Τιμή (€)"] = pd.to_numeric(edited_all["Τιμή (€)"], errors="coerce").fillna(0.0)
                            edited_all["Σύνολο (€)"] = edited_all["Ποσότητα"] * edited_all["Τιμή (€)"]

                            oids = df_s_view["order_id"].tolist()
                            orders_all = load_orders().copy()
                            for j, oid in enumerate(oids):
                                if oid not in orders_all["order_id"].astype(str).tolist():
                                    continue
                                rowj = edited_all.iloc[j]
                                orders_all.loc[orders_all["order_id"]==oid, "date"] = pd.to_datetime(rowj["Ημερομηνία"])
                                orders_all.loc[orders_all["order_id"]==oid, ["product","qty","unit_price","total"]] = [
                                    str(rowj["Προϊόν"]).strip(),
                                    int(rowj["Ποσότητα"]),
                                    float(rowj["Τιμή (€)"]),
                                    float(rowj["Σύνολο (€)"]),
                                ]
                            save_orders(orders_all)
                            st.success("Αποθηκεύτηκαν οι αλλαγές.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Σφάλμα αποθήκευσης: {e}")
                with cdel:
                    labels = df_s_view.apply(lambda r: f"{pd.to_datetime(r['Ημερομηνία']).date()} • {r['Προϊόν']} (qty {int(r['Ποσότητα'])})", axis=1).tolist()
                    del_sel = st.multiselect("Διαγραφή γραμμών (επιλογή)", labels, key="del_sel_student_lines")
                    confirm = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="confirm_del_student_lines")
                    if st.button("🗑️ Διαγραφή επιλεγμένων γραμμών") and del_sel and confirm:
                        to_del_oids = [df_s_view.iloc[k]["order_id"] for k, lab in enumerate(labels) if lab in del_sel]
                        orders_all = load_orders().copy()
                        orders_all = orders_all[~orders_all["order_id"].isin(to_del_oids)]
                        save_orders(orders_all)
                        if not is_admin:
                            st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x not in to_del_oids]
                        st.success(f"Διαγράφηκαν {len(to_del_oids)} γραμμές.")
                        st.rerun()

            st.divider()
            st.markdown("#### Επεξεργασία μίας γραμμής (προαιρετικά)")
            df = df.sort_values("date", ascending=False).reset_index(drop=True)
            df["label"] = df.apply(lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['product']} (qty {int(r['qty']) if pd.notna(r['qty']) and int(pd.to_numeric(r['qty'], errors='coerce') or 0) > 0 else ''})", axis=1)
            mapping = dict(zip(df["label"], df["order_id"]))
            choice = st.selectbox("Διάλεξε γραμμή", df["label"].tolist())
            oid = mapping[choice]
            row = df[df["order_id"]==oid].iloc[0]

            with st.form("edit_line"):
                col1, col2, col3, col4, col5 = st.columns([1.2,1.5,2,1,1])
                with col1:
                    new_date = st.date_input("Ημερομηνία", value=row["date"].date() if pd.notna(row["date"]) else date.today())
                with col2:
                    students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
                    current_label = f"{row['student']} — {row['school']} — {row['class']}".strip(" —")
                    sel_list = students["label"].tolist()
                    idx = sel_list.index(current_label) if current_label in sel_list else 0
                    new_label = st.selectbox("Μαθητής/-τρια", sel_list, index=idx)
                with col3:
                    prods = products["product"].tolist()
                    idxp = prods.index(row["product"]) if row["product"] in prods else 0
                    new_product = st.selectbox("Προϊόν", prods, index=idxp)
                with col4:
                    base_qty = int(row["qty"]) if pd.notna(row["qty"]) and int(pd.to_numeric(row["qty"], errors="coerce") or 0) > 0 else 1
                    new_qty = st.number_input("Ποσότητα", min_value=1, step=1, value=base_qty)
                with col5:
                    auto_price = float(products.loc[products["product"]==new_product, "price"].iloc[0]) if (products["product"]==new_product).any() else float(row["unit_price"] or 0.0)
                    new_price = st.number_input("Τιμή", min_value=0.0, step=0.1, value=float(auto_price), format="%.2f")
                b1, b2, _ = st.columns([1,1,6])
                with b1:
                    save_btn = st.form_submit_button("💾 Αποθήκευση αλλαγών")
                with b2:
                    del_btn = st.form_submit_button("🗑️ Διαγραφή γραμμής")

            if save_btn:
                orders_all = load_orders().copy()
                orders_all.loc[orders_all["order_id"]==oid, "date"] = pd.to_datetime(new_date)
                parts = new_label.split(" — ")
                ns = parts[0]; nsch = parts[1] if len(parts)>1 else ""; ncl = parts[2] if len(parts)>2 else ""
                orders_all.loc[orders_all["order_id"]==oid, ["student","school","class"]] = [ns, nsch, ncl]
                orders_all.loc[orders_all["order_id"]==oid, ["product","qty","unit_price","total"]] = [new_product, new_qty, new_price, new_qty*new_price]
                save_orders(orders_all)
                st.success("Οι αλλαγές αποθηκεύτηκαν.")
                st.rerun()

            if del_btn:
                orders_all = load_orders().copy()
                orders_all = orders_all[orders_all["order_id"]!=oid]
                save_orders(orders_all)
                st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x != oid]
                st.success("Η γραμμή διαγράφηκε.")
                st.rerun()

# ---------------- Σύνοψη ----------------
elif page == "Σύνοψη":
    st.subheader("Σύνοψη & Αναφορές")
    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
        col_date1, col_date2 = st.columns(2)
        min_d = orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today()
        max_d = orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today()
        with col_date1:
            d_from = st.date_input("Από", value=min_d)
        with col_date2:
            d_to = st.date_input("Έως", value=max_d)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            students_filter = st.multiselect("Μαθητές/-τριες", sorted(orders["student"].dropna().unique().tolist()))
        with c2:
            products_filter = st.multiselect("Προϊόντα", sorted(orders["product"].dropna().unique().tolist()))
        with c3:
            schools_filter  = st.multiselect("Σχολεία", sorted(orders["school"].dropna().unique().tolist()))
        with c4:
            classes_filter  = st.multiselect("Τάξεις", sorted(orders["class"].dropna().unique().tolist()))

        df = orders.copy()
        df = df[(df["date"] >= pd.to_datetime(d_from)) & (df["date"] <= pd.to_datetime(d_to))]
        if students_filter: df = df[df["student"].isin(students_filter)]
        if products_filter: df = df[df["product"].isin(products_filter)]
        if schools_filter:  df = df[df["school"].isin(schools_filter)]
        if classes_filter:  df = df[df["class"].isin(classes_filter)]

        st.markdown("### Ανά μαθητή/-τρια")
        by_student = df.groupby(["student","school","class"], as_index=False).agg(
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values(["school","class","student"]).rename(columns={
            "student":"Μαθητής/-τρια","school":"Σχολείο","class":"Τάξη"
        })
        st.dataframe(by_student, use_container_width=True)

        st.markdown("### Ανά τάξη")
        by_class = df.groupby(["school","class"], as_index=False).agg(
            παραγγελίες=("order_id","count"),
            ποσότητα=("qty","sum"),
            σύνολο=("total","sum")
        ).sort_values(["school","class"]).rename(columns={"school":"Σχολείο","class":"Τάξη"})
        st.dataframe(by_class, use_container_width=True)

        st.markdown("### Ανά σχολείο")
        by_school = df.groupby(["school"], as_index=False).agg(
            παραγγελίες=("order_id","count"),
            ποσότητα=("qty","sum"),
            σύνολο=("total","sum")
        ).sort_values(["school"]).rename(columns={"school":"Σχολείο"})
        st.dataframe(by_school, use_container_width=True)

        st.markdown("### Ανά προϊόν (για κατάστημα)")
        by_product = df.groupby(["product"], as_index=False).agg(
            qty=("qty", "sum"),
            total=("total", "sum")
        ).sort_values("qty", ascending=False).rename(columns={
            "product":"Προϊόν","qty":"Ποσότητα","total":"Σύνολο (€)"
        })
        st.dataframe(by_product, use_container_width=True)

        # Excel export
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
            by_student.to_excel(writer, sheet_name="Ανά μαθητή", index=False)
            by_class.to_excel(writer, sheet_name="Ανά τάξη", index=False)
            by_school.to_excel(writer, sheet_name="Ανά σχολείο", index=False)
            by_product.to_excel(writer, sheet_name="Ανά προϊόν", index=False)
            df.sort_values(["school","class","student","date"]).rename(columns={
                "date":"Ημερομηνία","student":"Μαθητής/-τριες","school":"Σχολείο","class":"Τάξη",
                "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)","total":"Σύνολο (€)"
            }).to_excel(writer, sheet_name="Αναλυτικά", index=False)
        st.download_button("⬇️ Λήψη Excel", data=out.getvalue(), file_name="αναφορές.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        colp1, colp2, colp3, colp4 = st.columns(4)
        with colp1:
            if st.button("📄 PDF: Ανά μαθητή"):
            pdfbuf = pdf_by_student_summary(
                by_student,
                title="Αναφορά ανά μαθητή/τρια",
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_μαθητη.pdf", mime="application/pdf")
        with colp2:
            if st.button("📄 PDF: Ανά τάξη"):
            pdfbuf = pdf_by_class_summary(
                by_class,
                title="Αναφορά ανά τάξη",
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_ταξη.pdf", mime="application/pdf")
        with colp3:
            if st.button("📄 PDF: Ανά σχολείο"):
            pdfbuf = pdf_by_school_summary(
                by_school,
                title="Αναφορά ανά σχολείο",
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_σχολειο.pdf", mime="application/pdf")
        with colp4:
            if st.button("📄 PDF: Ανά προϊόν"):
            src = by_product.rename(columns={"Προϊόν": "product", "Ποσότητα": "qty", "Σύνολο (€)": "total"})
            pdfbuf = pdf_by_product_summary(
                src,
                title="Παραγγελία προς κατάστημα",
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_κατάστημα.pdf", mime="application/pdf")

        st.divider()
        st.markdown("### Μαζική διαγραφή από τα αναλυτικά")
        df_labels = df.sort_values(["date","student","product"]).copy()
        df_labels["label"] = df_labels.apply(lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['school']} • {r['class']} • {r['product']} (qty {int(r['qty']) if pd.notna(r['qty']) and int(r['qty'])>0 else 0})", axis=1)
        sel_bulk = st.multiselect("Επίλεξε γραμμές για διαγραφή", df_labels["label"].tolist(), key="summary_bulk_sel")
        confirm_bulk = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="summary_bulk_confirm")
        if st.button("🗑️ Διαγραφή επιλεγμένων (Σύνοψη)") and sel_bulk and confirm_bulk:
            oids = df_labels.loc[df_labels["label"].isin(sel_bulk), "order_id"].tolist()
            all_orders = load_orders().copy()
            all_orders = all_orders[~all_orders["order_id"].isin(oids)]
            save_orders(all_orders)
            if not is_admin:
                st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x not in oids]
            st.success(f"Διαγράφηκαν {len(oids)} γραμμές.")
            st.rerun()

# ---------------- Δελτία ----------------
elif page == "Δελτία":
    st.subheader("Δελτίο & Εκτύπωση PDF")
    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
        col_date1, col_date2 = st.columns(2)
        min_d = orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today()
        max_d = orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today()
        with col_date1:
            d_from = st.date_input("Από", value=min_d, key="b_from")
        with col_date2:
            d_to = st.date_input("Έως", value=max_d, key="b_to")

        c1, c2, c3 = st.columns(3)
        with c1:
            sel_school = st.selectbox("Σχολείο (ή Όλα)", ["Όλα"] + sorted(orders["school"].dropna().unique().tolist()))
        with c2:
            df_for = orders if sel_school=="Όλα" else orders[orders["school"]==sel_school]
            sel_class = st.selectbox("Τάξη (ή Όλες)", ["Όλες"] + sorted(df_for["class"].dropna().unique().tolist()))
        with c3:
            df_names = df_for if sel_class=="Όλες" else df_for[df_for["class"]==sel_class]
            sel_student = st.selectbox("Μαθητής/-τρια (ή Όλοι/-ες)", ["Όλοι/-ες"] + sorted(df_names["student"].dropna().unique().tolist()))

        df = orders.copy()
        df = df[(df["date"]>=pd.to_datetime(d_from)) & (df["date"]<=pd.to_datetime(d_to))]
        if sel_school != "Όλα": df = df[df["school"] == sel_school]
        if sel_class != "Όλες": df = df[df["class"] == sel_class]
        if sel_student != "Όλοι/-ες": df = df[df["student"] == sel_student]

        detail = df.groupby(["student","school","class","product","unit_price"], as_index=False).agg(
            qty=("qty","sum"),
            total=("total","sum")
        ).sort_values(["school","class","student","product"])
        st.dataframe(detail, use_container_width=True)

        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
            detail.to_excel(writer, sheet_name="Δελτίο", index=False)
        st.download_button("⬇️ Λήψη Excel", data=out.getvalue(), file_name="δελτιο.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if st.button("📄 Εξαγωγή PDF (ομαδοποιημένο ανά σχολείο/μαθητή)"):
            buffer = pdf_grouped_by_school_student(detail, title="Δελτίο Παραγγελιών")
            st.download_button("⬇️ Λήψη PDF", data=buffer.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")
