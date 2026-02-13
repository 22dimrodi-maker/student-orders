# app.py
# Παραγγελίες Μαθητών — Πλήρης, σταθερή έκδοση (modular)
# Streamlit Cloud friendly: αποθήκευση σε CSV στο repo (products.csv, students.csv, orders.csv)
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
# Fonts (PDF) — Greek-safe
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

# (optional) logo file inside repo root: logo.png
REPO_LOGO_PATH = DATA_DIR / "logo.png"

APP_URL = st.secrets.get("APP_URL", os.getenv("APP_URL", ""))
ADMIN_PIN = st.secrets.get("ADMIN_PIN", os.getenv("ADMIN_PIN", "1234"))
APP_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", ""))  # optional global login


# =========================
# Helpers
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
        df[c] = df[c].astype(str).str.strip()
    df = df[df["student"].str.len() > 0].drop_duplicates(subset=["student", "school", "class"])
    df = df.sort_values(["school", "class", "student"]).reset_index(drop=True)
    return df


def save_students(df: pd.DataFrame) -> None:
    out = df.copy()
    for c in ["student", "school", "class"]:
        if c not in out.columns:
            out[c] = ""
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

    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0.0)
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0.0)
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


def wrap2(s: str, width: int = 24) -> str:
    s = "" if s is None else str(s)
    parts = textwrap.wrap(s, width=width)
    if len(parts) <= 1:
        return s
    return parts[0] + "\n" + parts[1]


def currency(x) -> str:
    try:
        return f"{float(x):.2f} €"
    except Exception:
        return "0.00 €"


# =========================
# PDF utilities (common theme)
# =========================
def pdf_header(c: canvas.Canvas, title: str, logo_bytes: bytes | None):
    w, h = A4
    left, right = 2 * cm, w - 2 * cm
    top = h - 2 * cm

    # logo
    title_x = left
    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            c.drawImage(img, left, top - 1.2 * cm, width=1.2 * cm, height=1.2 * cm, preserveAspectRatio=True, mask="auto")
            title_x = left + 1.5 * cm
        except Exception:
            title_x = left

    c.setFont(FONT_BLD, 14)
    c.drawString(title_x, top, title)
    c.setFont(FONT_REG, 9)
    c.drawRightString(right, top, f"Ημερομηνία εξαγωγής: {date.today().isoformat()}")

    c.setLineWidth(0.5)
    c.line(left, top - 0.2 * cm, right, top - 0.2 * cm)
    return top - 0.9 * cm


def pdf_footer(c: canvas.Canvas, app_url: str):
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = 1.5 * cm

    c.setFont(FONT_REG, 8)
    c.drawString(left, y, f"Σελίδα {c.getPageNumber()}")
    c.drawRightString(right, y, f"Εκτύπωση: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if app_url and isinstance(app_url, str) and app_url.strip():
        try:
            q = qr.QrCode(app_url.strip(), barLevel="M")
            q.drawOn(c, right - 2.2 * cm, y - 1.8 * cm)
        except Exception:
            pass


def pdf_new_page(c: canvas.Canvas, title: str, logo_bytes: bytes | None, app_url: str):
    pdf_footer(c, app_url)
    c.showPage()
    return pdf_header(c, title, logo_bytes)


def pdf_by_student_summary(by_student: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)

    # fixed columns
    x_student = left
    x_school = left + 7.0 * cm
    x_class = left + 12.2 * cm
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_student, ypos, "Μαθητής/-τρια")
        c.drawString(x_school, ypos, "Σχολείο")
        c.drawString(x_class, ypos, "Τάξη")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)

    for _, r in by_student.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = head(y)

        student = wrap2(r.get("Μαθητής/-τρια", ""), width=26)
        school = str(r.get("Σχολείο", "") or "")
        clazz = str(r.get("Τάξη", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)

        s1, s2 = (student.split("\n") + [""])[:2]

        c.drawString(x_student, y, s1[:32])
        c.drawString(x_school, y, school[:26])
        c.drawString(x_class, y, clazz[:10])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

        if s2.strip():
            if y < 2.4 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)
                y = head(y)
            c.drawString(x_student, y, s2[:32])
            y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_class_summary(by_class: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_school = left
    x_class = left + 9.0 * cm
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_school, ypos, "Σχολείο")
        c.drawString(x_class, ypos, "Τάξη")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)

    for _, r in by_class.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)
            y = head(y)
        school = str(r.get("Σχολείο", "") or "")
        clazz = str(r.get("Τάξη", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)

        c.drawString(x_school, y, school[:44])
        c.drawString(x_class, y, clazz[:18])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_school_summary(by_school: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_school = left
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

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

        school = str(r.get("Σχολείο", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)

        c.drawString(x_school, y, school[:58])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_by_product_summary(by_product_df: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    # expects columns product, qty, total
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes)

    x_product = left
    x_qty_r = right - 3.0 * cm
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

        prod = str(r.get("product", "") or "")
        qty = int(float(r.get("qty", 0) or 0))
        tot = float(r.get("total", 0.0) or 0.0)

        c.drawString(x_product, y, prod[:60])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{tot:.2f}")
        y -= 0.40 * cm

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_bulletin_grouped(detail: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str):
    """
    PDF «Δελτίο Παραγγελιών» με fixed columns, ομαδοποίηση Σχολείο → Μαθητής/-τρια,
    διαχωρισμό μαθητών με γραμμή και κενό, και wrap 2 γραμμών στο προϊόν αν χρειαστεί.
    detail columns: student, school, class, product, unit_price, qty, total
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm

    y = pdf_header(c, title, logo_bytes)

    # fixed columns
    x_prod = left
    x_price_r = right - 7.0 * cm
    x_qty_r = right - 3.5 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos):
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_prod, ypos, "Προϊόν")
        c.drawRightString(x_price_r, ypos, "Τιμή (€)")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.45 * cm

    grand_total = 0.0

    for school, g_school in detail.groupby("school", dropna=False):
        if y < 3.0 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)

        c.setFont(FONT_BLD, 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.60 * cm

        school_total = 0.0

        for student, g_student in g_school.groupby("student", dropna=False):
            if y < 3.0 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)

            cls = str(g_student["class"].iloc[0] or "").strip()
            student_wrapped = wrap2(student, width=38)

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

            y = head(y)

            subtotal = 0.0
            c.setFont(FONT_REG, 9.5)

            for _, r in g_student.sort_values(["product"]).iterrows():
                if y < 2.4 * cm:
                    y = pdf_new_page(c, title, logo_bytes, app_url)
                    y = head(y)

                prod = str(r["product"])
                prod_lines = textwrap.wrap(prod, width=52)[:2] or [""]
                c.drawString(x_prod, y, prod_lines[0])
                c.drawRightString(x_price_r, y, f"{float(r['unit_price']):.2f}")
                c.drawRightString(x_qty_r, y, f"{int(r['qty'])}")
                c.drawRightString(x_total_r, y, f"{float(r['total']):.2f}")
                y -= 0.38 * cm

                if len(prod_lines) > 1:
                    if y < 2.4 * cm:
                        y = pdf_new_page(c, title, logo_bytes, app_url)
                        y = head(y)
                    c.drawString(x_prod, y, prod_lines[1])
                    y -= 0.38 * cm

                subtotal += float(r["total"])

            if y < 2.6 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url)

            c.setFont(FONT_BLD, 10)
            c.drawRightString(x_total_r, y, f"Σύνολο μαθητή/-τριας: {subtotal:.2f} €")
            y -= 0.40 * cm

            # separator
            c.setLineWidth(0.5)
            c.line(left, y, right, y)
            y -= 0.55 * cm

            school_total += subtotal

        if y < 2.6 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url)

        c.setFont(FONT_BLD, 11)
        c.drawRightString(right - 0.5 * cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.75 * cm

        grand_total += school_total

    if y < 2.6 * cm:
        y = pdf_new_page(c, title, logo_bytes, app_url)

    c.setFont(FONT_BLD, 12)
    c.drawRightString(right - 0.5 * cm, y, f"Γενικό Σύνολο: {grand_total:.2f} €")

    pdf_footer(c, app_url)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# =========================
# Sidebar: Role / Admin / Logo
# =========================
def get_default_logo_bytes():
    # priority: uploaded in session → repo logo.png → none
    if REPO_LOGO_PATH.exists():
        try:
            return REPO_LOGO_PATH.read_bytes()
        except Exception:
            return None
    return None


if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = get_default_logo_bytes()

if "my_order_ids" not in st.session_state:
    st.session_state["my_order_ids"] = []  # session-only ids for non-admin delete


role = st.sidebar.selectbox("Ρόλος", ["Καταχώριση", "Διαχειριστής"], index=0)

is_admin = False
if role == "Διαχειριστής":
    pin = st.sidebar.text_input("PIN Διαχειριστή", type="password")
    if str(pin) == str(ADMIN_PIN):
        is_admin = True
        st.sidebar.success("✅ Πρόσβαση διαχειριστή/ριας")
    else:
        st.sidebar.info("Πληκτρολόγησε PIN για λειτουργίες διαχείρισης.")

st.sidebar.markdown("### Εμφάνιση / PDF")
if is_admin:
    up_logo = st.sidebar.file_uploader("Λογότυπο (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if up_logo is not None:
        st.session_state["logo_bytes"] = up_logo.read()

app_url = st.sidebar.text_input("URL εφαρμογής (για QR)", value=APP_URL or "", disabled=not is_admin)
if st.session_state.get("logo_bytes"):
    st.sidebar.image(st.session_state["logo_bytes"], use_column_width=True)

with st.sidebar.expander("🔍 Διαγνωστικά"):
    st.write(f"products.csv: {'✅' if PRODUCTS_PATH.exists() else '❌'}")
    st.write(f"students.csv: {'✅' if STUDENTS_PATH.exists() else '❌'}")
    st.write(f"orders.csv: {'✅' if ORDERS_PATH.exists() else '❌'}")
    try:
        st.write(f"Προϊόντα: {len(load_products())}")
        st.write(f"Μαθητές/τριες: {len(load_students())}")
        st.write(f"Γραμμές παραγγελιών: {len(load_orders())}")
    except Exception as e:
        st.write("Σφάλμα φόρτωσης:", e)


# =========================
# Login gate (optional global password)
# =========================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if APP_PASSWORD and not st.session_state["logged_in"]:
    st.markdown("## Παραγγελίες Μαθητών")
    st.info("🔐 Η πρόσβαση στην εφαρμογή προστατεύεται με κωδικό.")
    pwd = st.text_input("Κωδικός πρόσβασης", type="password")
    if st.button("Είσοδος"):
        if str(pwd) == str(APP_PASSWORD):
            st.session_state["logged_in"] = True
            st.success("✅ Επιτυχής είσοδος")
            st.rerun()
        else:
            st.error("Λάθος κωδικός.")
    st.caption("Ο κωδικός ορίζεται ως APP_PASSWORD στα Streamlit Secrets (TOML).")
    st.stop()


# =========================
# Top bar
# =========================
c_logo, c_title = st.columns([1, 10])
with c_logo:
    if st.session_state.get("logo_bytes"):
        st.image(st.session_state["logo_bytes"], width=72)
with c_title:
    st.markdown("## Παραγγελίες Μαθητών")
    st.caption("Καταχώριση παραγγελιών • Αναφορές • PDF • Διαχείριση προϊόντων και μαθητών/τριών")


# =========================
# Navigation
# =========================
pages_admin = ["Παραγγελίες", "Σύνοψη", "Δελτία", "Κατάλογος", "Μαθητές"]
pages_user = ["Παραγγελίες", "Σύνοψη", "Δελτία"]
page = st.sidebar.radio("Μενού", pages_admin if is_admin else pages_user, index=0)


# =========================
# Page renderers (modular)
# =========================
def render_catalog(is_admin: bool):
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Κατάλογος προϊόντων")
    products = load_products().copy()

    with st.form("add_product_form"):
        c1, c2 = st.columns([3, 1])
        with c1:
            pname = st.text_input("Προϊόν", placeholder="π.χ. Club sandwich")
        with c2:
            price = st.number_input("Τιμή (€)", min_value=0.0, step=0.10, format="%.2f")
        add = st.form_submit_button("➕ Προσθήκη")

    if add and pname.strip():
        if (products["product"].str.lower() == pname.strip().lower()).any():
            st.warning("Υπάρχει ήδη προϊόν με αυτό το όνομα.")
        else:
            products.loc[len(products)] = [pname.strip(), float(price)]
            save_products(products)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("### Εισαγωγή προϊόντων από Excel")
    replace_all = st.checkbox("✅ Αντικατάσταση όλων των προϊόντων", value=False, key="rep_prod")
    up = st.file_uploader("Excel (στήλες: Προϊόν–Τιμή ή product–price)", type=["xlsx"], key="up_prod_excel")
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
            if replace_all:
                save_products(incoming)
                st.success("Έγινε αντικατάσταση προϊόντων.")
            else:
                save_products(pd.concat([products, incoming], ignore_index=True))
                st.success("Έγινε συγχώνευση προϊόντων.")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    products = load_products().copy()
    st.markdown("### Διαγραφή προϊόντων")
    if products.empty:
        st.info("Δεν υπάρχουν προϊόντα.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            one = st.selectbox("Μεμονωμένη διαγραφή", products["product"].tolist(), key="del_one_prod")
            conf = st.checkbox("✅ Επιβεβαίωση", key="conf_one_prod")
            if st.button("🗑️ Διαγραφή προϊόντος") and conf:
                products2 = products[products["product"] != one].reset_index(drop=True)
                save_products(products2)
                st.success(f"Διαγράφηκε: {one}")
                st.rerun()
        with c2:
            multi = st.multiselect("Μαζική διαγραφή", products["product"].tolist(), key="del_multi_prod")
            confm = st.checkbox("✅ Επιβεβαίωση μαζικής", key="conf_multi_prod")
            if st.button("🗑️ Διαγραφή επιλεγμένων") and confm and multi:
                products2 = products[~products["product"].isin(multi)].reset_index(drop=True)
                save_products(products2)
                st.success(f"Διαγράφηκαν: {len(multi)} προϊόντα")
                st.rerun()

    st.dataframe(products.rename(columns={"product": "Προϊόν", "price": "Τιμή (€)"}), use_container_width=True)


def render_students(is_admin: bool):
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Μαθητές/τριες")
    students = load_students().copy()

    with st.form("add_student_form"):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            sname = st.text_input("Ονοματεπώνυμο")
        with c2:
            school = st.text_input("Σχολείο", placeholder="π.χ. 1ο Γυμνάσιο")
        with c3:
            clazz = st.text_input("Τάξη", placeholder="π.χ. Β1")
        add = st.form_submit_button("➕ Προσθήκη")

    if add and sname.strip():
        exists = (
            (students["student"].str.lower() == sname.strip().lower())
            & (students["school"].str.lower() == school.strip().lower())
            & (students["class"].str.lower() == clazz.strip().lower())
        ).any()
        if exists:
            st.warning("Υπάρχει ήδη.")
        else:
            students.loc[len(students)] = [sname.strip(), school.strip(), clazz.strip()]
            save_students(students)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("### Εισαγωγή μαθητών/τριών από Excel")
    replace_all = st.checkbox("✅ Αντικατάσταση όλων των μαθητών/τριών", value=False, key="rep_students")
    up = st.file_uploader("Excel (Ονοματεπώνυμο–Σχολείο–Τάξη) ή (student–school–class)", type=["xlsx"], key="up_students_excel")
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
                    tmp = df.rename(columns={"ονοματεπώνυμο": "student", "σχολείο": "school", "τάξη": "class"})[["student", "school", "class"]]
                elif "student" in cols:
                    if "school" not in cols:
                        df["school"] = ""
                    if "class" not in cols:
                        df["class"] = ""
                    tmp = df.rename(columns={cols["student"]: "student", cols.get("school","school"): "school", cols.get("class","class"): "class"})[["student", "school", "class"]]
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
            if replace_all:
                save_students(incoming)
                st.success("Έγινε αντικατάσταση μαθητών/τριών.")
            else:
                save_students(pd.concat([students, incoming], ignore_index=True))
                st.success("Έγινε συγχώνευση μαθητών/τριών.")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    students = load_students().copy()
    st.markdown("### Διαγραφή μαθητών/τριών")
    if students.empty:
        st.info("Δεν υπάρχουν μαθητές/τριες.")
    else:
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}", axis=1)
        c1, c2 = st.columns(2)
        with c1:
            one = st.selectbox("Μεμονωμένη διαγραφή", students["label"].tolist(), key="del_one_student")
            conf = st.checkbox("✅ Επιβεβαίωση", key="conf_one_student")
            if st.button("🗑️ Διαγραφή μαθητή/-τριας") and conf:
                kept = students[students["label"] != one][["student", "school", "class"]]
                save_students(kept)
                st.success("Διαγράφηκε.")
                st.rerun()
        with c2:
            multi = st.multiselect("Μαζική διαγραφή", students["label"].tolist(), key="del_multi_student")
            confm = st.checkbox("✅ Επιβεβαίωση μαζικής", key="conf_multi_student")
            if st.button("🗑️ Διαγραφή επιλεγμένων μαθητών/τριών") and confm and multi:
                kept = students[~students["label"].isin(multi)][["student", "school", "class"]]
                save_students(kept)
                st.success(f"Διαγράφηκαν: {len(multi)} εγγραφές")
                st.rerun()

    st.dataframe(students.rename(columns={"student":"Ονοματεπώνυμο","school":"Σχολείο","class":"Τάξη"}), use_container_width=True)


def render_orders(is_admin: bool):
    st.subheader("Παραγγελίες")

    products = load_products()
    students = load_students()
    tabs = st.tabs(["🆕 Νέα παραγγελία", "✏️ Διόρθωση / Διαγραφή"])

    # ---------------- New order ----------------
    with tabs[0]:
        st.markdown("### Καταχώριση νέας παραγγελίας")

        if products.empty or students.empty:
            st.info("Χρειάζονται προϊόντα και μαθητές/τριες. Αν είσαι διαχειριστής/ρια, συμπλήρωσέ τα από τις αντίστοιχες καρτέλες.")
            return

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

        catalog = products["product"].tolist()
        price_map = dict(zip(products["product"], products["price"]))

        # editor state
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
            st.session_state["order_editor_df"] = pd.DataFrame(
                {"Προϊόν": ["", "", ""], "Ποσότητα": [1, 1, 1], "Μερικό (€)": [0.0, 0.0, 0.0]}
            )
            st.session_state["last_student_label"] = label

        # ---- FORM to avoid losing last row edits ----
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

            edited = edited.copy()
            edited["Ποσότητα"] = pd.to_numeric(edited.get("Ποσότητα", 1), errors="coerce").fillna(1).astype(int)
            edited["Ποσότητα"] = edited["Ποσότητα"].clip(lower=1)
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
                new_click = st.form_submit_button("🧹 Νέα παραγγελία")
            with b3:
                add_row = st.form_submit_button("➕ Προσθήκη γραμμής")

        # actions outside form
        sel_row = students_local.loc[students_local["label"] == label].iloc[0]
        s_name, s_school, s_class = sel_row["student"], sel_row["school"], sel_row["class"]

        if add_row:
            tmp = st.session_state["order_editor_df"].copy()
            tmp = pd.concat([tmp, pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})], ignore_index=True)
            st.session_state["order_editor_df"] = tmp
            st.rerun()

        if new_click:
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
                qty = max(1, qty)
                unit_price = float(price_map.get(p, 0.0))
                total = unit_price * qty
                oid = str(uuid.uuid4())
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
                all_orders = load_orders().copy()
                all_orders = pd.concat([all_orders, pd.DataFrame(new_rows)], ignore_index=True)
                save_orders(all_orders)
                st.session_state["my_order_ids"].extend(new_ids)
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1], "Μερικό (€)": [0.0]})
                st.success("✅ Η παραγγελία αποθηκεύτηκε.")
                st.rerun()

    # ---------------- Edit/Delete ----------------
    with tabs[1]:
        st.markdown("### Διόρθωση / Διαγραφή παραγγελιών")
        orders = load_orders().copy()
        if orders.empty:
            st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
            return

        # non-admin view restriction (optional)
        if not is_admin:
            only_mine = st.checkbox("Εμφάνιση μόνο των δικών μου καταχωρίσεων (συνεδρία)", value=True)
            if only_mine:
                ids = st.session_state.get("my_order_ids", [])
                orders = orders[orders["order_id"].isin(ids)].copy()

        if orders.empty:
            st.info("Δεν υπάρχουν διαθέσιμες γραμμές για διόρθωση/διαγραφή.")
            return

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
            return

        products_df = load_products()
        catalog = products_df["product"].tolist()

        st.markdown("#### Προβολή ανά μαθητή/-τρια (όλα τα είδη μαζί)")
        student_list = sorted(df["student"].dropna().unique().tolist())
        sel_student = st.selectbox("Μαθητής/-τρια", ["(επιλογή...)"] + student_list, key="edit_student_all")
        if sel_student != "(επιλογή...)":
            df_s = df[df["student"] == sel_student].copy().sort_values(["date", "product"])
            st.markdown(f"**Σύνολο μαθητή/-τριας:** {df_s['total'].sum():.2f} €")

            df_s_view = df_s.copy()
            df_s_view["Ημερομηνία"] = pd.to_datetime(df_s_view["date"], errors="coerce").dt.date
            df_s_view = df_s_view.rename(
                columns={
                    "school": "Σχολείο",
                    "class": "Τάξη",
                    "product": "Προϊόν",
                    "qty": "Ποσότητα",
                    "unit_price": "Τιμή (€)",
                    "total": "Σύνολο (€)",
                }
            )[["Ημερομηνία", "Σχολείο", "Τάξη", "Προϊόν", "Ποσότητα", "Τιμή (€)", "Σύνολο (€)", "order_id"]]

            editor = st.data_editor(
                df_s_view.drop(columns=["order_id"]),
                key="edit_lines_editor",
                num_rows="fixed",
                column_config={
                    "Ημερομηνία": st.column_config.DateColumn("Ημερομηνία"),
                    "Προϊόν": st.column_config.SelectboxColumn("Προϊόν", options=catalog),
                    "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1),
                    "Τιμή (€)": st.column_config.NumberColumn("Τιμή (€)", min_value=0.0, step=0.10, format="%.2f"),
                    "Σύνολο (€)": st.column_config.NumberColumn("Σύνολο (€)", disabled=True, format="%.2f"),
                },
                use_container_width=True,
            )

            csave, cdel = st.columns([1, 1])
            with csave:
                if st.button("💾 Αποθήκευση αλλαγών"):
                    try:
                        oids = df_s_view["order_id"].tolist()
                        edited2 = editor.copy()
                        edited2["Ποσότητα"] = pd.to_numeric(edited2["Ποσότητα"], errors="coerce").fillna(1).astype(int).clip(lower=1)
                        edited2["Τιμή (€)"] = pd.to_numeric(edited2["Τιμή (€)"], errors="coerce").fillna(0.0).clip(lower=0.0)
                        edited2["Σύνολο (€)"] = edited2["Ποσότητα"] * edited2["Τιμή (€)"]

                        all_orders = load_orders().copy()
                        for i, oid in enumerate(oids):
                            rowi = edited2.iloc[i]
                            all_orders.loc[all_orders["order_id"] == oid, "date"] = pd.to_datetime(rowi["Ημερομηνία"])
                            all_orders.loc[all_orders["order_id"] == oid, ["product", "qty", "unit_price", "total"]] = [
                                str(rowi["Προϊόν"]).strip(),
                                int(rowi["Ποσότητα"]),
                                float(rowi["Τιμή (€)"]),
                                float(rowi["Σύνολο (€)"]),
                            ]
                        save_orders(all_orders)
                        st.success("Αποθηκεύτηκαν οι αλλαγές.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Σφάλμα: {e}")

            with cdel:
                labels = df_s_view.apply(
                    lambda r: f"{r['Ημερομηνία']} • {r['Προϊόν']} (qty {int(r['Ποσότητα'])})",
                    axis=1,
                ).tolist()
                del_sel = st.multiselect("Διαγραφή γραμμών", labels, key="del_sel_lines")
                conf = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="conf_del_lines")
                if st.button("🗑️ Διαγραφή επιλεγμένων") and conf and del_sel:
                    del_oids = [df_s_view.iloc[i]["order_id"] for i, lab in enumerate(labels) if lab in del_sel]
                    all_orders = load_orders().copy()
                    all_orders = all_orders[~all_orders["order_id"].isin(del_oids)]
                    save_orders(all_orders)
                    if not is_admin:
                        st.session_state["my_order_ids"] = [x for x in st.session_state.get("my_order_ids", []) if x not in del_oids]
                    st.success(f"Διαγράφηκαν {len(del_oids)} γραμμές.")
                    st.rerun()

        st.divider()
        st.markdown("#### Μαζική διαγραφή (από τα φίλτρα)")
        df2 = df.sort_values(["date", "student", "product"]).copy()
        df2["label"] = df2.apply(
            lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['school']} • {r['class']} • {r['product']} (qty {int(r['qty'])})",
            axis=1,
        )
        pick = st.multiselect("Επίλεξε γραμμές", df2["label"].tolist(), key="bulk_pick")
        confb = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="bulk_conf")
        if st.button("🗑️ Διαγραφή επιλεγμένων γραμμών") and confb and pick:
            del_oids = df2.loc[df2["label"].isin(pick), "order_id"].tolist()
            all_orders = load_orders().copy()
            all_orders = all_orders[~all_orders["order_id"].isin(del_oids)]
            save_orders(all_orders)
            if not is_admin:
                st.session_state["my_order_ids"] = [x for x in st.session_state.get("my_order_ids", []) if x not in del_oids]
            st.success(f"Διαγράφηκαν {len(del_oids)} γραμμές.")
            st.rerun()


def render_summary(is_admin: bool):
    st.subheader("Σύνοψη & Αναφορές")
    orders = load_orders().copy()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        return

    # date range filter
    min_d = orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today()
    max_d = orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today()

    c1, c2 = st.columns(2)
    with c1:
        d_from = st.date_input("Από", value=min_d, key="sum_from")
    with c2:
        d_to = st.date_input("Έως", value=max_d, key="sum_to")

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

    st.markdown(f"**Σύνολο επιλογής:** {df['total'].sum():.2f} €")

    by_student = (
        df.groupby(["student", "school", "class"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school", "class", "student"])
        .rename(columns={"student": "Μαθητής/-τρια", "school": "Σχολείο", "class": "Τάξη"})
    )

    by_class = (
        df.groupby(["school", "class"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school", "class"])
        .rename(columns={"school": "Σχολείο", "class": "Τάξη"})
    )

    by_school = (
        df.groupby(["school"], as_index=False)
        .agg(ποσότητα=("qty", "sum"), σύνολο=("total", "sum"))
        .sort_values(["school"])
        .rename(columns={"school": "Σχολείο"})
    )

    by_product = (
        df.groupby(["product"], as_index=False)
        .agg(qty=("qty", "sum"), total=("total", "sum"))
        .sort_values("qty", ascending=False)
        .rename(columns={"product": "Προϊόν", "qty": "Ποσότητα", "total": "Σύνολο (€)"})
    )

    st.markdown("### Ανά μαθητή/-τρια")
    st.dataframe(by_student, use_container_width=True)

    st.markdown("### Ανά τάξη")
    st.dataframe(by_class, use_container_width=True)

    st.markdown("### Ανά σχολείο")
    st.dataframe(by_school, use_container_width=True)

    st.markdown("### Ανά προϊόν (για κατάστημα)")
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
    st.markdown("### PDF αναφορές (fixed layout)")

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        if st.button("📄 PDF: Ανά μαθητή", key="pdf_student"):
            pdfbuf = pdf_by_student_summary(
                by_student, "Αναφορά ανά μαθητή/τρια", st.session_state.get("logo_bytes"), app_url
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_μαθητη.pdf", mime="application/pdf")

    with p2:
        if st.button("📄 PDF: Ανά τάξη", key="pdf_class"):
            pdfbuf = pdf_by_class_summary(
                by_class, "Αναφορά ανά τάξη", st.session_state.get("logo_bytes"), app_url
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_ταξη.pdf", mime="application/pdf")

    with p3:
        if st.button("📄 PDF: Ανά σχολείο", key="pdf_school"):
            pdfbuf = pdf_by_school_summary(
                by_school, "Αναφορά ανά σχολείο", st.session_state.get("logo_bytes"), app_url
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_σχολειο.pdf", mime="application/pdf")

    with p4:
        if st.button("📄 PDF: Ανά προϊόν", key="pdf_product"):
            src = by_product.rename(columns={"Προϊόν": "product", "Ποσότητα": "qty", "Σύνολο (€)": "total"})
            pdfbuf = pdf_by_product_summary(
                src, "Παραγγελία προς κατάστημα", st.session_state.get("logo_bytes"), app_url
            )
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_κατάστημα.pdf", mime="application/pdf")


def render_bulletins(is_admin: bool):
    st.subheader("Δελτίο Παραγγελιών (PDF)")
    orders = load_orders().copy()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        return

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
        sel_school = st.selectbox("Σχολείο (ή Όλα)", ["Όλα"] + sorted(df["school"].dropna().unique().tolist()), key="b_school")
    with c2:
        df_for = df if sel_school == "Όλα" else df[df["school"] == sel_school]
        sel_class = st.selectbox("Τάξη (ή Όλες)", ["Όλες"] + sorted(df_for["class"].dropna().unique().tolist()), key="b_class")
    with c3:
        df_for2 = df_for if sel_class == "Όλες" else df_for[df_for["class"] == sel_class]
        sel_student = st.selectbox("Μαθητής/-τρια (ή Όλοι/-ες)", ["Όλοι/-ες"] + sorted(df_for2["student"].dropna().unique().tolist()), key="b_student")

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

    st.dataframe(
        detail.rename(columns={
            "student":"Μαθητής/-τρια",
            "school":"Σχολείο",
            "class":"Τάξη",
            "product":"Προϊόν",
            "unit_price":"Τιμή (€)",
            "qty":"Ποσότητα",
            "total":"Σύνολο (€)",
        }),
        use_container_width=True
    )

    # Excel
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        detail.to_excel(writer, sheet_name="Δελτίο", index=False)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.download_button(
            "⬇️ Λήψη Excel",
            data=out.getvalue(),
            file_name="δελτιο.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with c2:
        if st.button("📄 Εξαγωγή PDF (ομαδοποίηση ανά σχολείο/μαθητή)"):
            pdfbuf = pdf_bulletin_grouped(detail, "Δελτίο Παραγγελιών", st.session_state.get("logo_bytes"), app_url)
            st.download_button("⬇️ Λήψη PDF", data=pdfbuf.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")


# =========================
# Dispatch
# =========================
PAGE_RENDERERS = {
    "Παραγγελίες": render_orders,
    "Σύνοψη": render_summary,
    "Δελτία": render_bulletins,
    "Κατάλογος": render_catalog,
    "Μαθητές": render_students,
}

renderer = PAGE_RENDERERS.get(page)
if renderer is None:
    st.error("Άγνωστη σελίδα.")
else:
    renderer(is_admin=is_admin)
