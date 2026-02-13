# app.py
# Streamlit app: Παραγγελίες Μαθητών (multi-school) — σταθερή έκδοση
import os
import io
import uuid
import textwrap
from pathlib import Path
from datetime import date, datetime

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.graphics.barcode import qr
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================
# Page config
# =========================
st.set_page_config(page_title="Παραγγελίες Μαθητών", layout="wide")


# =========================
# Fonts for PDF (Greek-safe)
# =========================
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    FONT_REG = "DejaVuSans"
    FONT_BLD = "DejaVuSans-Bold"
except Exception:
    FONT_REG = "Helvetica"
    FONT_BLD = "Helvetica-Bold"


# =========================
# Paths & Secrets
# =========================
DATA_DIR = Path(".")
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
ORDERS_PATH = DATA_DIR / "orders.csv"

DEFAULT_LOGO = Path("/mnt/data/logo (2).png")  # local placeholder in this environment

APP_URL = st.secrets.get("APP_URL", os.getenv("APP_URL", "https://your-app-url-here"))
ADMIN_PIN = st.secrets.get("ADMIN_PIN", os.getenv("ADMIN_PIN", "1234"))
APP_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", ""))  # optional global login


# =========================
# Utilities
# =========================
def _safe_clear_cache(fn):
    try:
        fn.clear()
    except Exception:
        pass


def ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PRODUCTS_PATH.exists():
        pd.DataFrame(columns=["product", "price"]).to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    if not STUDENTS_PATH.exists():
        pd.DataFrame(columns=["student", "school", "class"]).to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    if not ORDERS_PATH.exists():
        pd.DataFrame(
            columns=["order_id", "date", "student", "school", "class", "product", "qty", "unit_price", "total"]
        ).to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")


ensure_files()


@st.cache_data
def load_products() -> pd.DataFrame:
    df = pd.read_csv(PRODUCTS_PATH) if PRODUCTS_PATH.exists() else pd.DataFrame(columns=["product", "price"])
    if "product" not in df.columns:
        df["product"] = ""
    if "price" not in df.columns:
        df["price"] = 0.0
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df[df["product"].str.len() > 0].drop_duplicates(subset=["product"]).sort_values("product")
    return df.reset_index(drop=True)


def save_products(df: pd.DataFrame) -> None:
    out = df.copy()
    if "product" not in out.columns:
        out["product"] = ""
    if "price" not in out.columns:
        out["price"] = 0.0
    out = out[["product", "price"]].copy()
    out["product"] = out["product"].astype(str).str.strip()
    out["price"] = pd.to_numeric(out["price"], errors="coerce").fillna(0.0)
    out = out[out["product"].str.len() > 0].drop_duplicates(subset=["product"]).sort_values("product")
    out.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    _safe_clear_cache(load_products)


@st.cache_data
def load_students() -> pd.DataFrame:
    df = pd.read_csv(STUDENTS_PATH) if STUDENTS_PATH.exists() else pd.DataFrame(columns=["student", "school", "class"])
    for c in ["student", "school", "class"]:
        if c not in df.columns:
            df[c] = ""
    for c in ["student", "school", "class"]:
        df[c] = df[c].astype(str).str.strip()
    df = df[df["student"].str.len() > 0].drop_duplicates(subset=["student", "school", "class"])
    df = df.sort_values(["school", "class", "student"]).reset_index(drop=True)
    return df


def save_students(df: pd.DataFrame) -> None:
    out = df.copy()
    for c in ["student", "school", "class"]:
        if c not in out.columns:
            out[c] = ""
    out = out[["student", "school", "class"]].copy()
    for c in ["student", "school", "class"]:
        out[c] = out[c].astype(str).str.strip()
    out = out[out["student"].str.len() > 0].drop_duplicates(subset=["student", "school", "class"])
    out = out.sort_values(["school", "class", "student"]).reset_index(drop=True)
    out.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    _safe_clear_cache(load_students)


@st.cache_data
def load_orders() -> pd.DataFrame:
    df = (
        pd.read_csv(ORDERS_PATH, parse_dates=["date"])
        if ORDERS_PATH.exists()
        else pd.DataFrame(columns=["order_id", "date", "student", "school", "class", "product", "qty", "unit_price", "total"])
    )
    for c in ["order_id", "date", "student", "school", "class", "product", "qty", "unit_price", "total"]:
        if c not in df.columns:
            df[c] = pd.NA
    df["order_id"] = df["order_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["student", "school", "class", "product"]:
        df[c] = df[c].astype(str).str.strip()
    for c in ["qty", "unit_price", "total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df.reset_index(drop=True)


def save_orders(df: pd.DataFrame) -> None:
    cols = ["order_id", "date", "student", "school", "class", "product", "qty", "unit_price", "total"]
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[cols].copy()
    out.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    _safe_clear_cache(load_orders)


def wrap2(text: str, width: int = 24) -> str:
    s = "" if text is None else str(text)
    parts = textwrap.wrap(s, width=width)
    if len(parts) <= 1:
        return s
    return parts[0] + "\n" + parts[1]


# =========================
# PDF rendering
# =========================
def pdf_header(c: canvas.Canvas, title: str, logo_bytes: bytes | None):
    w, h = A4
    left, right = 2 * cm, w - 2 * cm
    top = h - 2 * cm

    title_x = left
    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            c.drawImage(img, left, top - 1.2 * cm, width=1.2 * cm, height=1.2 * cm, preserveAspectRatio=True, mask="auto")
            title_x = left + 1.4 * cm
        except Exception:
            title_x = left

    c.setFont(FONT_BLD, 14)
    c.drawString(title_x, top, title)
    c.setFont(FONT_REG, 9)
    c.drawRightString(right, top, f"Ημερομηνία εξαγωγής: {date.today().isoformat()}")
    return top - 0.8 * cm


def pdf_footer(c: canvas.Canvas, app_url: str):
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    bottom = 1.5 * cm

    c.setFont(FONT_REG, 8)
    c.drawString(left, bottom, f"Σελίδα {c.getPageNumber()}")
    c.drawRightString(right, bottom, f"Εκτύπωση: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if app_url and isinstance(app_url, str) and app_url.strip():
        try:
            q = qr.QrCode(app_url.strip(), barLevel="M")
            q.drawOn(c, right - 2.2 * cm, bottom - 1.8 * cm)
        except Exception:
            pass


def pdf_new_page(c: canvas.Canvas, title: str, logo_bytes: bytes | None, app_url: str):
    pdf_footer(c, app_url)
    c.showPage()
    return pdf_header(c, title, logo_bytes)


def pdf_table(df: pd.DataFrame, title: str, columns: list[tuple[str, str, str]], logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)
    step = (right - left) / max(1, len(columns))

    def draw_head(ypos: float) -> float:
        c.setFont(FONT_BLD, 9)
        for i, (_key, head, _al) in enumerate(columns):
            c.drawString(left + i * step, ypos, str(head)[:28])
        c.setFont(FONT_REG, 9)
        return ypos - 0.45 * cm

    y = draw_head(y)

    for _, row in df.iterrows():
        if y < 2.3 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = draw_head(y)

        max_h = 0.38 * cm
        for i, (key, _head, align) in enumerate(columns):
            val = row.get(key, "")
            s = "" if pd.isna(val) else str(val)
            # allow two lines
            if "\n" in s:
                l1, l2 = (s.split("\n") + [""])[:2]
                if align == "R":
                    c.drawRightString(left + (i + 1) * step - 2, y, l1[:26])
                    c.drawRightString(left + (i + 1) * step - 2, y - 0.32 * cm, l2[:26])
                else:
                    c.drawString(left + i * step, y, l1[:28])
                    c.drawString(left + i * step, y - 0.32 * cm, l2[:28])
                max_h = max(max_h, 0.60 * cm)
            else:
                if align == "R":
                    c.drawRightString(left + (i + 1) * step - 2, y, s[:26])
                else:
                    c.drawString(left + i * step, y, s[:28])
        y -= max_h

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_grouped_by_school_student(detail: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)
    grand_total = 0.0

    for school, g_school in detail.groupby("school", dropna=False):
        if y < 3 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)

        c.setFont(FONT_BLD, 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.6 * cm

        school_total = 0.0
        for student, g_student in g_school.groupby("student", dropna=False):
            if y < 3 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)

            cls = str(g_student["class"].iloc[0] or "").strip()
            student_wrapped = wrap2(student, width=34)
            c.setFont(FONT_BLD, 11)
            c.drawString(left, y, "Μαθητής/-τρια:")
            c.setFont(FONT_REG, 11)
            c.drawString(left + 3.2 * cm, y, student_wrapped.split("\n")[0])
            y -= 0.45 * cm
            if "\n" in student_wrapped:
                c.drawString(left + 3.2 * cm, y, student_wrapped.split("\n")[1])
                y -= 0.45 * cm
            if cls:
                c.setFont(FONT_REG, 10)
                c.drawString(left + 3.2 * cm, y, f"Τάξη: {cls}")
                y -= 0.45 * cm

            # table header
            c.setFont(FONT_BLD, 9)
            c.drawString(left, y, "Προϊόν")
            c.drawRightString(right - 6.5 * cm, y, "Τιμή (€)")
            c.drawRightString(right - 3.5 * cm, y, "Ποσότητα")
            c.drawRightString(right - 0.5 * cm, y, "Σύνολο (€)")
            y -= 0.4 * cm
            c.setFont(FONT_REG, 9)

            subtotal = 0.0
            for _, r in g_student.sort_values(["product"]).iterrows():
                if y < 2.3 * cm:
                    y = pdf_new_page(c, title, logo_bytes, app_url)
                    c.setFont(FONT_BLD, 9)
                    c.drawString(left, y, "Προϊόν")
                    c.drawRightString(right - 6.5 * cm, y, "Τιμή (€)")
                    c.drawRightString(right - 3.5 * cm, y, "Ποσότητα")
                    c.drawRightString(right - 0.5 * cm, y, "Σύνολο (€)")
                    y -= 0.4 * cm
                    c.setFont(FONT_REG, 9)

                c.drawString(left, y, str(r["product"])[:44])
                c.drawRightString(right - 6.5 * cm, y, f"{float(r['unit_price']):.2f}")
                c.drawRightString(right - 3.5 * cm, y, f"{int(r['qty'])}")
                c.drawRightString(right - 0.5 * cm, y, f"{float(r['total']):.2f}")
                y -= 0.35 * cm
                subtotal += float(r["total"])

            if y < 2.3 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)

            c.setFont(FONT_BLD, 10)
            c.drawRightString(right - 0.5 * cm, y, f"Σύνολο μαθητή/-τριας: {subtotal:.2f} €")
            y -= 0.35 * cm

            # separator line + blank
            c.setLineWidth(0.5)
            c.line(left, y, right, y)
            y -= 0.55 * cm

            c.setFont(FONT_REG, 9)
            school_total += subtotal

        if y < 2.3 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)

        c.setFont(FONT_BLD, 11)
        c.drawRightString(right - 0.5 * cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.7 * cm
        grand_total += school_total

    if y < 2.3 * cm:
        y = pdf_new_page(c, title, logo_bytes, app_url)

    c.setFont(FONT_BLD, 12)
    c.drawRightString(right - 0.5 * cm, y, f"Γενικό Σύνολο: {grand_total:.2f} €")

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_products_report(by_product: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)

    c.setFont(FONT_BLD, 10)
    c.drawString(left, y, "Προϊόν")
    c.drawRightString(right - 3 * cm, y, "Σύνολο Ποσότητας")
    c.drawRightString(right - 0.5 * cm, y, "Σύνολο (€)")
    y -= 0.5 * cm

    c.setFont(FONT_REG, 10)
    for _, r in by_product.iterrows():
        if y < 2.3 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            c.setFont(FONT_BLD, 10)
            c.drawString(left, y, "Προϊόν")
            c.drawRightString(right - 3 * cm, y, "Σύνολο Ποσότητας")
            c.drawRightString(right - 0.5 * cm, y, "Σύνολο (€)")
            y -= 0.5 * cm
            c.setFont(FONT_REG, 10)

        c.drawString(left, y, str(r["product"])[:52])
        c.drawRightString(right - 3 * cm, y, f"{int(r['qty'])}")
        c.drawRightString(right - 0.5 * cm, y, f"{float(r['total']):.2f}")
        y -= 0.4 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# =========================
# Sidebar: Role + Logo
# =========================
if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = DEFAULT_LOGO.read_bytes() if DEFAULT_LOGO.exists() else None

role = st.sidebar.selectbox("Ρόλος", ["Καταχώριση", "Διαχειριστής"], index=0)
is_admin = False
if role == "Διαχειριστής":
    pin = st.sidebar.text_input("PIN Διαχειριστή", type="password")
    if str(pin) == str(ADMIN_PIN):
        is_admin = True
        st.sidebar.success("✅ Διαχειριστής/ρια")
    else:
        st.sidebar.warning("Πληκτρολόγησε σωστό PIN για λειτουργίες διαχείρισης.")

st.sidebar.markdown("### Ρυθμίσεις εμφάνισης")
if is_admin:
    up_logo = st.sidebar.file_uploader("Ανέβασμα λογοτύπου (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if up_logo is not None:
        st.session_state["logo_bytes"] = up_logo.read()
app_url = st.sidebar.text_input("URL εφαρμογής (για QR)", value=APP_URL if is_admin else APP_URL, disabled=not is_admin)

if st.session_state.get("logo_bytes"):
    st.sidebar.image(st.session_state["logo_bytes"], caption="Λογότυπο", use_column_width=True)

with st.sidebar.expander("🔍 Διαγνωστικά"):
    try:
        st.write(f"- products.csv: {'✅' if PRODUCTS_PATH.exists() else '❌'}")
        st.write(f"- students.csv: {'✅' if STUDENTS_PATH.exists() else '❌'}")
        st.write(f"- orders.csv: {'✅' if ORDERS_PATH.exists() else '❌'}")
        st.write(f"Προϊόντα: {len(load_products())} • Μαθητές/τριες: {len(load_students())} • Γραμμές: {len(load_orders())}")
    except Exception as e:
        st.write("Σφάλμα:", e)


# =========================
# Login gate (optional)
# =========================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if APP_PASSWORD and not st.session_state["logged_in"]:
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


# =========================
# Top bar
# =========================
col_logo, col_title = st.columns([1, 8])
with col_logo:
    if st.session_state.get("logo_bytes"):
        st.image(st.session_state["logo_bytes"], width=64)
with col_title:
    st.markdown("## Παραγγελίες Μαθητών")
    st.caption("Καταχώριση παραγγελιών, διαχείριση μαθητών/τριών & προϊόντων, εξαγωγές PDF/Excel.")


# =========================
# Navigation
# =========================
pages_admin = ["Παραγγελίες", "Σύνοψη", "Δελτία", "Κατάλογος", "Μαθητές"]
pages_user = ["Παραγγελίες", "Σύνοψη", "Δελτία"]
page = st.sidebar.radio("Μενού", pages_admin if is_admin else pages_user, index=0)


# =========================
# Page: Κατάλογος (Admin)
# =========================
if page == "Κατάλογος":
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Τιμοκατάλογος")
    products = load_products().copy()

    with st.form("add_product"):
        c1, c2 = st.columns([3, 1])
        with c1:
            p = st.text_input("Προϊόν", placeholder="π.χ. Club sandwich")
        with c2:
            pr = st.number_input("Τιμή (€)", min_value=0.0, step=0.1, format="%.2f")
        add_ok = st.form_submit_button("➕ Προσθήκη")
    if add_ok and p.strip():
        if (products["product"].str.lower() == p.strip().lower()).any():
            st.warning("Υπάρχει ήδη προϊόν με αυτό το όνομα.")
        else:
            products.loc[len(products)] = [p.strip(), pr]
            save_products(products)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("### Εισαγωγή από Excel προϊόντων")
    replace_products = st.checkbox("✅ Αντικατάσταση όλων των προϊόντων", value=False)
    up = st.file_uploader("Excel (στήλες: Προϊόν – Τιμή) ή (product – price)", type=["xlsx"])
    if up is not None:
        try:
            xl = pd.ExcelFile(up)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                cols = {str(c).strip().lower(): c for c in df.columns}
                if "προϊόν" in cols and "τιμή" in cols:
                    tmp = df.rename(columns={cols["προϊόν"]: "product", cols["τιμή"]: "price"})[["product", "price"]]
                elif "product" in cols and "price" in cols:
                    tmp = df.rename(columns={cols["product"]: "product", cols["price"]: "price"})[["product", "price"]]
                else:
                    tmp = df.iloc[:, :2].copy()
                    tmp.columns = ["product", "price"]
                frames.append(tmp)
            incoming = pd.concat(frames, ignore_index=True)
            if replace_products:
                save_products(incoming)
                st.success("Έγινε αντικατάσταση όλων των προϊόντων από το Excel.")
            else:
                save_products(pd.concat([products, incoming], ignore_index=True))
                st.success("Ο κατάλογος ενημερώθηκε από το Excel (συγχώνευση).")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    st.markdown("### Διαγραφή προϊόντων")
    if not products.empty:
        one = st.selectbox("Μεμονωμένη διαγραφή", products["product"].tolist())
        conf1 = st.checkbox("✅ Επιβεβαίωση μεμονωμένης", key="conf_del_prod1")
        if st.button("🗑️ Διαγραφή προϊόντος") and conf1:
            products = products[products["product"] != one].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκε: {one}")
            st.rerun()

        multi = st.multiselect("Μαζική διαγραφή", products["product"].tolist())
        conf2 = st.checkbox("✅ Επιβεβαίωση μαζικής", key="conf_del_prod2")
        if st.button("🗑️ Διαγραφή επιλεγμένων") and conf2 and multi:
            products = products[~products["product"].isin(multi)].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκαν: {len(multi)} προϊόντα")
            st.rerun()

    st.dataframe(products.rename(columns={"product": "Προϊόν", "price": "Τιμή (€)"}), use_container_width=True)


# =========================
# Page: Μαθητές (Admin)
# =========================
elif page == "Μαθητές":
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Μαθητές/τριες")
    students = load_students().copy()

    with st.form("add_student"):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            s = st.text_input("Ονοματεπώνυμο")
        with c2:
            sch = st.text_input("Σχολείο", placeholder="π.χ. 1ο Γυμνάσιο")
        with c3:
            cl = st.text_input("Τάξη", placeholder="π.χ. Β1")
        add_ok = st.form_submit_button("➕ Προσθήκη")
    if add_ok and s.strip():
        exists = (
            (students["student"].str.lower() == s.strip().lower())
            & (students["school"].str.lower() == sch.strip().lower())
            & (students["class"].str.lower() == cl.strip().lower())
        ).any()
        if exists:
            st.warning("Υπάρχει ήδη.")
        else:
            students.loc[len(students)] = [s.strip(), sch.strip(), cl.strip()]
            save_students(students)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("### Εισαγωγή μαθητών/τριών από Excel")
    replace_students = st.checkbox("✅ Αντικατάσταση όλων των μαθητών/τριών", value=False)
    up = st.file_uploader("Excel (Ονοματεπώνυμο – Σχολείο – Τάξη) ή (student – school – class)", type=["xlsx"])
    if up is not None:
        try:
            xl = pd.ExcelFile(up)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                cols = {str(c).strip().lower(): c for c in df.columns}
                if "ονοματεπώνυμο" in cols:
                    if "σχολείο" not in cols:
                        df["σχολείο"] = ""
                    if "τάξη" not in cols:
                        df["τάξη"] = ""
                    tmp = df.rename(columns={"ονοματεπώνυμο": "student", "σχολείο": "school", "τάξη": "class"})[
                        ["student", "school", "class"]
                    ]
                elif "student" in cols:
                    if "school" not in cols:
                        df["school"] = ""
                    if "class" not in cols:
                        df["class"] = ""
                    tmp = df.rename(columns={cols["student"]: "student", cols.get("school", "school"): "school", cols.get("class", "class"): "class"})[
                        ["student", "school", "class"]
                    ]
                else:
                    tmp = df.copy()
                    if tmp.shape[1] >= 3:
                        tmp = tmp.iloc[:, :3]
                        tmp.columns = ["student", "school", "class"]
                    elif tmp.shape[1] == 2:
                        tmp = tmp.iloc[:, :2]
                        tmp.columns = ["student", "school"]
                        tmp["class"] = ""
                    else:
                        tmp = tmp.iloc[:, :1]
                        tmp.columns = ["student"]
                        tmp["school"] = ""
                        tmp["class"] = ""
                frames.append(tmp[["student", "school", "class"]])
            incoming = pd.concat(frames, ignore_index=True)
            if replace_students:
                save_students(incoming)
                st.success("Έγινε αντικατάσταση όλων των μαθητών/τριών από το Excel.")
            else:
                save_students(pd.concat([students, incoming], ignore_index=True))
                st.success("Η λίστα ενημερώθηκε από το Excel (συγχώνευση).")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    students = load_students().copy()
    if not students.empty:
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}", axis=1)

        st.markdown("### Διαγραφή μαθητών/τριών")
        one = st.selectbox("Μεμονωμένη διαγραφή", students["label"].tolist())
        conf1 = st.checkbox("✅ Επιβεβαίωση μεμονωμένης", key="conf_del_st1")
        if st.button("🗑️ Διαγραφή μαθητή/-τριας") and conf1:
            students2 = students[students["label"] != one][["student", "school", "class"]]
            save_students(students2)
            st.success("Διαγράφηκε.")
            st.rerun()

        multi = st.multiselect("Μαζική διαγραφή", students["label"].tolist())
        conf2 = st.checkbox("✅ Επιβεβαίωση μαζικής", key="conf_del_st2")
        if st.button("🗑️ Διαγραφή επιλεγμένων μαθητών/τριών") and conf2 and multi:
            students2 = students[~students["label"].isin(multi)][["student", "school", "class"]]
            save_students(students2)
            st.success(f"Διαγράφηκαν: {len(multi)} εγγραφές")
            st.rerun()

    st.dataframe(load_students().rename(columns={"student": "Ονοματεπώνυμο", "school": "Σχολείο", "class": "Τάξη"}), use_container_width=True)


# =========================
# Page: Παραγγελίες
# =========================
elif page == "Παραγγελίες":
    products = load_products()
    students = load_students()

    tabs = st.tabs(["🆕 Νέα παραγγελία", "✏️ Διόρθωση / Διαγραφή"])

    # -------- New order --------
    with tabs[0]:
        st.subheader("Καταχώριση νέας παραγγελίας")

        if products.empty or students.empty:
            st.info("Χρειάζονται προϊόντα και μαθητές/τριες. Αν είσαι διαχειριστής/ρια, συμπλήρωσέ τα από ‘Κατάλογος’ και ‘Μαθητές’.")
        else:
            students_local = students.copy()

            sort_mode = st.radio(
                "Ταξινόμηση μαθητών/τριών",
                ["Αλφαβητικά", "Ανά σχολείο → τάξη → αλφαβητικά", "Ανά τάξη → αλφαβητικά"],
                horizontal=True,
                index=1,
                key="sort_mode_entry",
            )

            if sort_mode == "Αλφαβητικά":
                students_local = students_local.sort_values(["student", "school", "class"], na_position="last")
            elif sort_mode == "Ανά τάξη → αλφαβητικά":
                students_local = students_local.sort_values(["class", "student", "school"], na_position="last")
            else:
                students_local = students_local.sort_values(["school", "class", "student"], na_position="last")

            students_local["label"] = students_local.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}", axis=1)

            # session state for editor rows
            if "order_editor_df" not in st.session_state:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
            if "last_student_label" not in st.session_state:
                st.session_state["last_student_label"] = None

            c1, c2 = st.columns([1.2, 3])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today(), key="order_date")
            with c2:
                label = st.selectbox("Μαθητής/-τρια", students_local["label"].tolist(), key="order_student")

            if st.session_state["last_student_label"] != label:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": ["", "", ""], "Ποσότητα": [1, 1, 1], "Μερικό (€)": [0.0, 0.0, 0.0]})
                st.session_state["last_student_label"] = label

            catalog = products["product"].tolist()
            price_map = dict(zip(products["product"], products["price"]))

            # IMPORTANT: Use st.form so the last edit is not lost on submit
            with st.form("order_form", clear_on_submit=False):
                edited = st.data_editor(
                    st.session_state["order_editor_df"],
                    key="order_editor",
                    num_rows="dynamic",
                    column_config={
                        "Προϊόν": st.column_config.SelectboxColumn("Προϊόν", options=catalog, required=False),
                        "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1),
                        "Μερικό (€)": st.column_config.NumberColumn("Μερικό (€)", format="%.2f", disabled=True),
                    },
                    use_container_width=True,
                )

                # Recompute line totals safely
                edited = edited.copy()
                edited["Ποσότητα"] = pd.to_numeric(edited.get("Ποσότητα", 1), errors="coerce").fillna(1).astype(int)
                edited["Προϊόν"] = edited.get("Προϊόν", "").astype(str)

                def _line_total(r):
                    p = str(r.get("Προϊόν", "")).strip()
                    q = int(r.get("Ποσότητα", 1))
                    return float(price_map.get(p, 0.0)) * q

                edited["Μερικό (€)"] = edited.apply(_line_total, axis=1)
                st.session_state["order_editor_df"] = edited

                subtotal = float(edited["Μερικό (€)"].sum()) if "Μερικό (€)" in edited.columns else 0.0
                st.markdown(f"**Σύνολο τρέχουσας παραγγελίας:** {subtotal:.2f} €")

                b1, b2, b3 = st.columns([1, 1, 2])
                with b1:
                    save_click = st.form_submit_button("✅ Καταχώριση παραγγελίας")
                with b2:
                    clear_click = st.form_submit_button("🧹 Νέα παραγγελία")
                with b3:
                    add_row = st.form_submit_button("➕ Προσθήκη γραμμής")

            # Handle form actions (outside the form)
            # Identify selected student
            sel_row = students_local.loc[students_local["label"] == label].iloc[0]
            s_name, s_school, s_class = sel_row["student"], sel_row["school"], sel_row["class"]

            if add_row:
                tmp = st.session_state["order_editor_df"].copy()
                tmp = pd.concat([tmp, pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})], ignore_index=True)
                st.session_state["order_editor_df"] = tmp
                st.rerun()

            if clear_click:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
                st.rerun()

            if save_click:
                editor_df = st.session_state["order_editor_df"].copy()
                new_rows = []
                new_ids = []

                for _, r in editor_df.iterrows():
                    p = str(r.get("Προϊόν", "")).strip()
                    if not p or p not in catalog:
                        continue
                    qty = int(r.get("Ποσότητα", 1))
                    unit_price = float(price_map.get(p, 0.0))
                    oid = str(uuid.uuid4())
                    total = unit_price * qty
                    new_rows.append(
                        {
                            "order_id": oid,
                            "date": pd.to_datetime(d),
                            "student": s_name,
                            "school": s_school,
                            "class": s_class,
                            "product": p,
                            "qty": qty,
                            "unit_price": unit_price,
                            "total": total,
                        }
                    )
                    new_ids.append(oid)

                if not new_rows:
                    st.warning("Δεν βρέθηκαν έγκυρες γραμμές προϊόντων για αποθήκευση.")
                else:
                    orders_all = load_orders().copy()
                    orders_all = pd.concat([orders_all, pd.DataFrame(new_rows)], ignore_index=True)
                    save_orders(orders_all)

                    # remember "my" lines for non-admin delete (session only)
                    st.session_state.setdefault("my_last_orders", [])
                    st.session_state["my_last_orders"].extend(new_ids)

                    st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
                    st.success("Η παραγγελία αποθηκεύτηκε.")
                    st.rerun()

    # -------- Edit/Delete --------
    with tabs[1]:
        st.subheader("Διόρθωση / Διαγραφή")

        orders = load_orders().copy()
        products = load_products()
        students = load_students()

        if orders.empty:
            st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        else:
            # non-admin: allow only session lines (optional)
            if not is_admin:
                only_mine = st.checkbox("Εμφάνιση μόνο των δικών μου καταχωρίσεων (συνεδρία)", value=True)
                if only_mine:
                    ids = st.session_state.get("my_last_orders", [])
                    orders = orders[orders["order_id"].isin(ids)].copy()

            # filters
            c1, c2, c3 = st.columns(3)
            with c1:
                f_student = st.multiselect("Μαθητές/-τριες", sorted(orders["student"].dropna().unique().tolist()))
            with c2:
                f_school = st.multiselect("Σχολεία", sorted(orders["school"].dropna().unique().tolist()))
            with c3:
                f_class = st.multiselect("Τάξεις", sorted(orders["class"].dropna().unique().tolist()))

            df = orders.copy()
            if f_student:
                df = df[df["student"].isin(f_student)]
            if f_school:
                df = df[df["school"].isin(f_school)]
            if f_class:
                df = df[df["class"].isin(f_class)]

            if df.empty:
                st.info("Δεν βρέθηκαν γραμμές με αυτά τα φίλτρα.")
            else:
                # 1) Show all lines for a selected student
                st.markdown("### Προβολή ανά μαθητή/-τρια (όλα τα είδη μαζί)")
                stus = sorted(df["student"].dropna().unique().tolist())
                sel_student_all = st.selectbox("Μαθητής/-τρια", ["(επιλογή...)"] + stus, key="edit_student_all")
                if sel_student_all != "(επιλογή...)":
                    df_s = df[df["student"] == sel_student_all].copy().sort_values(["date", "product"])
                    df_s["Ημερομηνία"] = pd.to_datetime(df_s["date"], errors="coerce").dt.date
                    df_s_view = df_s.rename(
                        columns={
                            "school": "Σχολείο",
                            "class": "Τάξη",
                            "product": "Προϊόν",
                            "qty": "Ποσότητα",
                            "unit_price": "Τιμή (€)",
                            "total": "Σύνολο (€)",
                        }
                    )[["Ημερομηνία", "Σχολείο", "Τάξη", "Προϊόν", "Ποσότητα", "Τιμή (€)", "Σύνολο (€)", "order_id"]]

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
                        use_container_width=True,
                    )

                    csave, cdel = st.columns([1, 1])
                    with csave:
                        if st.button("💾 Αποθήκευση αλλαγών (όλες οι γραμμές)"):
                            try:
                                edited_all2 = edited_all.copy()
                                edited_all2["Ποσότητα"] = pd.to_numeric(edited_all2["Ποσότητα"], errors="coerce").fillna(1).astype(int)
                                edited_all2["Τιμή (€)"] = pd.to_numeric(edited_all2["Τιμή (€)"], errors="coerce").fillna(0.0)
                                edited_all2["Σύνολο (€)"] = edited_all2["Ποσότητα"] * edited_all2["Τιμή (€)"]

                                oids = df_s_view["order_id"].tolist()
                                orders_all = load_orders().copy()
                                for j, oid in enumerate(oids):
                                    rowj = edited_all2.iloc[j]
                                    orders_all.loc[orders_all["order_id"] == oid, "date"] = pd.to_datetime(rowj["Ημερομηνία"])
                                    orders_all.loc[orders_all["order_id"] == oid, ["product", "qty", "unit_price", "total"]] = [
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
                        labels = df_s_view.apply(
                            lambda r: f"{r['Ημερομηνία']} • {r['Προϊόν']} (qty {int(r['Ποσότητα'])})",
                            axis=1,
                        ).tolist()
                        del_sel = st.multiselect("Διαγραφή γραμμών", labels, key="del_sel_student_lines")
                        conf = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="conf_del_student_lines")
                        if st.button("🗑️ Διαγραφή επιλεγμένων γραμμών") and conf and del_sel:
                            del_oids = [df_s_view.iloc[i]["order_id"] for i, lab in enumerate(labels) if lab in del_sel]
                            orders_all = load_orders().copy()
                            orders_all = orders_all[~orders_all["order_id"].isin(del_oids)]
                            save_orders(orders_all)
                            if not is_admin:
                                st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x not in del_oids]
                            st.success(f"Διαγράφηκαν {len(del_oids)} γραμμές.")
                            st.rerun()

                st.divider()

                # 2) Bulk delete from filtered df
                st.markdown("### Μαζική διαγραφή γραμμών (από τα φίλτρα)")
                df2 = df.sort_values(["date", "student", "product"]).copy()
                df2["label"] = df2.apply(
                    lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['school']} • {r['class']} • {r['product']} (qty {int(r['qty'])})",
                    axis=1,
                )
                bulk_sel = st.multiselect("Επίλεξε γραμμές", df2["label"].tolist(), key="bulk_orders_select")
                conf_bulk = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="bulk_orders_confirm")
                if st.button("🗑️ Διαγραφή επιλεγμένων παραγγελιών") and conf_bulk and bulk_sel:
                    del_oids = df2.loc[df2["label"].isin(bulk_sel), "order_id"].tolist()
                    orders_all = load_orders().copy()
                    orders_all = orders_all[~orders_all["order_id"].isin(del_oids)]
                    save_orders(orders_all)
                    if not is_admin:
                        st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x not in del_oids]
                    st.success(f"Διαγράφηκαν {len(del_oids)} γραμμές.")
                    st.rerun()


# =========================
# Page: Σύνοψη
# =========================
elif page == "Σύνοψη":
    st.subheader("Σύνοψη & Αναφορές")
    orders = load_orders().copy()

    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        st.stop()

    min_d = orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today()
    max_d = orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today()

    c1, c2 = st.columns(2)
    with c1:
        d_from = st.date_input("Από", value=min_d)
    with c2:
        d_to = st.date_input("Έως", value=max_d)

    df = orders[(orders["date"] >= pd.to_datetime(d_from)) & (orders["date"] <= pd.to_datetime(d_to))].copy()

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        students_filter = st.multiselect("Μαθητές/-τριες", sorted(df["student"].dropna().unique().tolist()))
    with f2:
        products_filter = st.multiselect("Προϊόντα", sorted(df["product"].dropna().unique().tolist()))
    with f3:
        schools_filter = st.multiselect("Σχολεία", sorted(df["school"].dropna().unique().tolist()))
    with f4:
        classes_filter = st.multiselect("Τάξεις", sorted(df["class"].dropna().unique().tolist()))

    if students_filter:
        df = df[df["student"].isin(students_filter)]
    if products_filter:
        df = df[df["product"].isin(products_filter)]
    if schools_filter:
        df = df[df["school"].isin(schools_filter)]
    if classes_filter:
        df = df[df["class"].isin(classes_filter)]

    st.markdown("### Ανά μαθητή/-τρια")
    by_student = (
        df.groupby(["student", "school", "class"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school", "class", "student"])
        .rename(columns={"student": "Μαθητής/-τρια", "school": "Σχολείο", "class": "Τάξη"})
    )
    st.dataframe(by_student, use_container_width=True)

    st.markdown("### Ανά τάξη")
    by_class = (
        df.groupby(["school", "class"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school", "class"])
        .rename(columns={"school": "Σχολείο", "class": "Τάξη"})
    )
    st.dataframe(by_class, use_container_width=True)

    st.markdown("### Ανά σχολείο")
    by_school = (
        df.groupby(["school"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school"])
        .rename(columns={"school": "Σχολείο"})
    )
    st.dataframe(by_school, use_container_width=True)

    st.markdown("### Ανά προϊόν (για κατάστημα)")
    by_product = (
        df.groupby(["product"], as_index=False)
        .agg(qty=("qty", "sum"), total=("total", "sum"))
        .sort_values("qty", ascending=False)
        .rename(columns={"product": "Προϊόν", "qty": "Ποσότητα", "total": "Σύνολο (€)"})
    )
    st.dataframe(by_product, use_container_width=True)

    # Excel export
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        by_student.to_excel(writer, sheet_name="Ανά μαθητή", index=False)
        by_class.to_excel(writer, sheet_name="Ανά τάξη", index=False)
        by_school.to_excel(writer, sheet_name="Ανά σχολείο", index=False)
        by_product.to_excel(writer, sheet_name="Ανά προϊόν", index=False)

        df_export = df.sort_values(["school", "class", "student", "date"]).rename(
            columns={
                "date": "Ημερομηνία",
                "student": "Μαθητής/-τρια",
                "school": "Σχολείο",
                "class": "Τάξη",
                "product": "Προϊόν",
                "qty": "Ποσότητα",
                "unit_price": "Τιμή (€)",
                "total": "Σύνολο (€)",
            }
        )
        df_export.to_excel(writer, sheet_name="Αναλυτικά", index=False)

    st.download_button(
        "⬇️ Λήψη Excel αναφορών",
        data=out.getvalue(),
        file_name="αναφορές.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    st.markdown("### PDF αναφορές")

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        if st.button("📄 PDF: Ανά μαθητή"):
            by_student_pdf = by_student.copy()
            by_student_pdf["Μαθητής/-τρια"] = by_student_pdf["Μαθητής/-τρια"].apply(lambda x: wrap2(x, width=24))
            pdfbuf = pdf_table(
                by_student_pdf,
                title="Αναφορά ανά μαθητή/τρια",
                columns=[
                    ("Μαθητής/-τρια", "Μαθητής/-τρια", "L"),
                    ("Σχολείο", "Σχολείο", "L"),
                    ("Τάξη", "Τάξη", "L"),
                    ("ποσότητα", "Ποσότητα", "R"),
                    ("σύνολο", "Σύνολο (€)", "R"),
                ],
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_μαθητη.pdf", mime="application/pdf")

    with p2:
        if st.button("📄 PDF: Ανά τάξη"):
            pdfbuf = pdf_table(
                by_class,
                title="Αναφορά ανά τάξη",
                columns=[
                    ("Σχολείο", "Σχολείο", "L"),
                    ("Τάξη", "Τάξη", "L"),
                    ("ποσότητα", "Ποσότητα", "R"),
                    ("σύνολο", "Σύνολο (€)", "R"),
                ],
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_ταξη.pdf", mime="application/pdf")

    with p3:
        if st.button("📄 PDF: Ανά σχολείο"):
            pdfbuf = pdf_table(
                by_school,
                title="Αναφορά ανά σχολείο",
                columns=[
                    ("Σχολείο", "Σχολείο", "L"),
                    ("ποσότητα", "Ποσότητα", "R"),
                    ("σύνολο", "Σύνολο (€)", "R"),
                ],
                logo_bytes=st.session_state.get("logo_bytes"),
                app_url=app_url,
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_σχολειο.pdf", mime="application/pdf")

    with p4:
        if st.button("📄 PDF: Ανά προϊόν"):
            src = by_product.rename(columns={"Προϊόν": "product", "Ποσότητα": "qty", "Σύνολο (€)": "total"})
            pdfbuf = pdf_products_report(src, title="Παραγγελία προς κατάστημα", logo_bytes=st.session_state.get("logo_bytes"), app_url=app_url)
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_κατάστημα.pdf", mime="application/pdf")


# =========================
# Page: Δελτία
# =========================
elif page == "Δελτία":
    st.subheader("Δελτίο & Εκτύπωση PDF")
    orders = load_orders().copy()

    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        st.stop()

    min_d = orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today()
    max_d = orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today()

    c1, c2 = st.columns(2)
    with c1:
        d_from = st.date_input("Από", value=min_d, key="b_from")
    with c2:
        d_to = st.date_input("Έως", value=max_d, key="b_to")

    df = orders[(orders["date"] >= pd.to_datetime(d_from)) & (orders["date"] <= pd.to_datetime(d_to))].copy()

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_school = st.selectbox("Σχολείο (ή Όλα)", ["Όλα"] + sorted(df["school"].dropna().unique().tolist()))
    with c2:
        df_for = df if sel_school == "Όλα" else df[df["school"] == sel_school]
        sel_class = st.selectbox("Τάξη (ή Όλες)", ["Όλες"] + sorted(df_for["class"].dropna().unique().tolist()))
    with c3:
        df_for2 = df_for if sel_class == "Όλες" else df_for[df_for["class"] == sel_class]
        sel_student = st.selectbox("Μαθητής/-τρια (ή Όλοι/-ες)", ["Όλοι/-ες"] + sorted(df_for2["student"].dropna().unique().tolist()))

    if sel_school != "Όλα":
        df = df[df["school"] == sel_school]
    if sel_class != "Όλες":
        df = df[df["class"] == sel_class]
    if sel_student != "Όλοι/-ες":
        df = df[df["student"] == sel_student]

    detail = (
        df.groupby(["student", "school", "class", "product", "unit_price"], as_index=False)
        .agg(qty=("qty", "sum"), total=("total", "sum"))
        .sort_values(["school", "class", "student", "product"])
    )

    st.dataframe(detail.rename(columns={"student":"Μαθητής/-τρια","school":"Σχολείο","class":"Τάξη","product":"Προϊόν","unit_price":"Τιμή (€)","qty":"Ποσότητα","total":"Σύνολο (€)"}), use_container_width=True)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        detail.to_excel(writer, sheet_name="Δελτίο", index=False)
    st.download_button("⬇️ Λήψη Excel", data=out.getvalue(), file_name="δελτιο.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if st.button("📄 Εξαγωγή PDF (ομαδοποιημένο ανά σχολείο/μαθητή)"):
        buffer = pdf_grouped_by_school_student(detail, title="Δελτίο Παραγγελιών", logo_bytes=st.session_state.get("logo_bytes"), app_url=app_url)
        st.download_button("⬇️ Λήψη PDF", data=buffer.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")
