# app.py — Student Orders (stable, modular, single-file)
# Features:
# - Students (name, school, class) + Products (name, price)
# - Orders: multiple items per student, live price/line totals/subtotal, save without extra selection
# - Edit/Delete orders (view all lines for selected student)
# - Reports (tables + PDF): by student / by class / by school / by product + Bulletin PDF grouped by school->student
# - Minimal neutral PDF theme, fixed columns, logo top-left, optional QR top-right (admin toggle), footer page + timestamp
# - Backup/Restore ZIP (admin), Quick backup button, snapshots on every save
# - Simple login password stored in app constants (option 2 as requested)
#
# Data files in app folder:
#   products.csv, students.csv, orders.csv, backups/*
#
# NOTE (Streamlit Cloud): local writes may not persist across redeploys. Use Backup ZIP before changes.

from __future__ import annotations

import io
import os
import json
import uuid
import zipfile
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
# Simple credentials (Option 2)
# =========================
APP_PASSWORD = "12345"   # change this
ADMIN_PIN = "4321"       # change this (admin features)

APP_TITLE = "Παραγγελίες Μαθητών"
APP_URL_DEFAULT = ""     # optional, used for QR if you want


# =========================
# Page config
# =========================
st.set_page_config(page_title=APP_TITLE, layout="wide")


# =========================
# PDF fonts (Greek-safe)
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
# Paths
# =========================
DATA_DIR = Path(".")
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
ORDERS_PATH = DATA_DIR / "orders.csv"
BACKUPS_DIR = DATA_DIR / "backups"
LAST_BACKUP_PATH = BACKUPS_DIR / "last_backup.txt"
REPO_LOGO_PATH = DATA_DIR / "logo.png"  # optional file in repo root


# =========================
# File init
# =========================
def ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(exist_ok=True)

    if not PRODUCTS_PATH.exists():
        pd.DataFrame(columns=["product", "price"]).to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    if not STUDENTS_PATH.exists():
        pd.DataFrame(columns=["student", "school", "class"]).to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    if not ORDERS_PATH.exists():
        pd.DataFrame(columns=[
            "order_id", "date", "student", "school", "class",
            "product", "qty", "unit_price", "total"
        ]).to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")


ensure_files()


# =========================
# Cache helpers
# =========================
def _safe_clear_cache(fn) -> None:
    try:
        fn.clear()  # type: ignore[attr-defined]
    except Exception:
        pass


@st.cache_data
def load_products() -> pd.DataFrame:
    df = pd.read_csv(PRODUCTS_PATH) if PRODUCTS_PATH.exists() else pd.DataFrame(columns=["product", "price"])
    if "product" not in df.columns:
        df["product"] = ""
    if "price" not in df.columns:
        df["price"] = 0.0
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df[df["product"].str.len() > 0].drop_duplicates(subset=["product"]).sort_values("product").reset_index(drop=True)
    return df


def save_products(df: pd.DataFrame) -> None:
    out = df.copy()
    if "product" not in out.columns:
        out["product"] = ""
    if "price" not in out.columns:
        out["price"] = 0.0
    out = out[["product", "price"]].copy()
    out["product"] = out["product"].astype(str).str.strip()
    out["price"] = pd.to_numeric(out["price"], errors="coerce").fillna(0.0)
    out = out[out["product"].str.len() > 0].drop_duplicates(subset=["product"]).sort_values("product").reset_index(drop=True)
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
    df = pd.read_csv(ORDERS_PATH) if ORDERS_PATH.exists() else pd.DataFrame(columns=[
        "order_id", "date", "student", "school", "class",
        "product", "qty", "unit_price", "total"
    ])
    # normalize
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

    # snapshot (best-effort)
    try:
        BACKUPS_DIR.mkdir(exist_ok=True)
        snap = BACKUPS_DIR / f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        out.to_csv(snap, index=False, encoding="utf-8-sig")
    except Exception:
        pass

    _safe_clear_cache(load_orders)


def currency(x) -> str:
    try:
        return f"{float(x):.2f} €"
    except Exception:
        return "0.00 €"


def wrap_lines(s: str, width: int, max_lines: int = 2) -> list[str]:
    s = "" if s is None else str(s)
    lines = textwrap.wrap(s, width=width) or [""]
    return lines[:max_lines]

def dfs_to_xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Δημιουργεί ένα Excel (.xlsx) in-memory με πολλαπλά φύλλα."""
    mem = io.BytesIO()
    with pd.ExcelWriter(mem, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe_name = str(sheet_name)[:31] or "Sheet1"
            (df if df is not None else pd.DataFrame()).to_excel(writer, index=False, sheet_name=safe_name)
    mem.seek(0)
    return mem.getvalue()



# =========================
# Backup / Restore
# =========================
def _read_last_backup_ts() -> str:
    try:
        if LAST_BACKUP_PATH.exists():
            return LAST_BACKUP_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _write_last_backup_ts(ts: str) -> None:
    try:
        BACKUPS_DIR.mkdir(exist_ok=True)
        LAST_BACKUP_PATH.write_text(ts, encoding="utf-8")
    except Exception:
        pass


def make_backup_zip() -> tuple[bytes, str]:
    """
    Δημιουργεί backup ZIP από ΤΑ ΤΡΕΧΟΝΤΑ δεδομένα (DataFrames) και όχι με απλή ανάγνωση αρχείων.
    Αυτό προστατεύει από περιπτώσεις όπου το repo/deploy έχει αντικαταστήσει τα CSV στον δίσκο.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Πάντα από τα loaders (ώστε να πάρουμε ό,τι "βλέπει" η εφαρμογή τώρα)
    orders_df = load_orders().copy()
    students_df = load_students().copy()
    products_df = load_products().copy()

    info = {
        "created_at": ts,
        "files": ["orders.csv", "students.csv", "products.csv"],
        "counts": {
            "orders_rows": int(len(orders_df)),
            "students_rows": int(len(students_df)),
            "products_rows": int(len(products_df)),
        },
    }

    def _csv_bytes(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("orders.csv", _csv_bytes(orders_df))
        zf.writestr("students.csv", _csv_bytes(students_df))
        zf.writestr("products.csv", _csv_bytes(products_df))
        zf.writestr("backup_info.json", json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"))

    mem.seek(0)
    _write_last_backup_ts(ts)
    return mem.getvalue(), ts


def restore_backup_zip(zip_bytes: bytes) -> str:
    mem = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(mem, mode="r") as zf:
        names = set(zf.namelist())
        needed = {"orders.csv", "students.csv", "products.csv"}
        if not needed.issubset(names):
            raise ValueError("Μη έγκυρο backup: λείπουν αρχεία (orders/students/products).")
        ORDERS_PATH.write_bytes(zf.read("orders.csv"))
        STUDENTS_PATH.write_bytes(zf.read("students.csv"))
        PRODUCTS_PATH.write_bytes(zf.read("products.csv"))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if "backup_info.json" in names:
            try:
                info = json.loads(zf.read("backup_info.json").decode("utf-8"))
                ts = str(info.get("created_at", ts))
            except Exception:
                pass
        _write_last_backup_ts(ts)
    _safe_clear_cache(load_orders)
    _safe_clear_cache(load_students)
    _safe_clear_cache(load_products)
    return "✅ Η επαναφορά ολοκληρώθηκε."


# =========================
# PDF theme (minimal, neutral)
# =========================
def pdf_footer(c: canvas.Canvas) -> None:
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = 1.4 * cm
    c.setFont(FONT_REG, 8)
    c.drawString(left, y, f"Σελίδα {c.getPageNumber()}")
    c.drawRightString(right, y, f"Εκτύπωση: {datetime.now().strftime('%Y-%m-%d %H:%M')}")


def pdf_header(c: canvas.Canvas, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> float:
    w, h = A4
    left, right = 2 * cm, w - 2 * cm
    top = h - 1.8 * cm

    # logo (top-left)
    title_x = left
    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            logo_w = 1.35 * cm
            logo_h = 1.35 * cm
            logo_y = h - 1.55 * cm
            c.drawImage(img, left, logo_y, width=logo_w, height=logo_h, preserveAspectRatio=True, mask="auto")
            title_x = left + 1.75 * cm
        except Exception:
            title_x = left

    # QR (top-right)
    qr_box = 1.35 * cm
    qr_drawn = False
    if qr_enabled and app_url and app_url.strip():
        try:
            q = qr.QrCode(app_url.strip(), barLevel="M")
            q.drawOn(c, right - qr_box, h - 1.55 * cm)
            qr_drawn = True
        except Exception:
            qr_drawn = False

    # Title
    c.setFont(FONT_BLD, 14)
    c.drawString(title_x, top, title)

    # Date (shift left if QR present)
    c.setFont(FONT_REG, 9)
    if qr_drawn:
        c.drawRightString(right - (qr_box + 0.2 * cm), top, f"Ημερομηνία εξαγωγής: {date.today().isoformat()}")
    else:
        c.drawRightString(right, top, f"Ημερομηνία εξαγωγής: {date.today().isoformat()}")

    # Divider line
    c.setLineWidth(0.4)
    c.line(left, top - 0.25 * cm, right, top - 0.25 * cm)
    return top - 0.9 * cm


def pdf_new_page(c: canvas.Canvas, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> float:
    pdf_footer(c)
    c.showPage()
    return pdf_header(c, title, logo_bytes, app_url, qr_enabled)


# ---- PDF: by student summary (fixed columns, wrap student to 2 lines) ----
def pdf_report_by_student(by_student: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> io.BytesIO:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes, app_url, qr_enabled)

    # fixed columns
    x_student = left
    x_school = left + 7.2 * cm
    x_class = left + 12.4 * cm
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos: float) -> float:
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
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
            y = head(y)

        student = str(r.get("Μαθητής/-τρια", "") or "")
        s_lines = wrap_lines(student, 28, 2)
        school = str(r.get("Σχολείο", "") or "")
        clazz = str(r.get("Τάξη", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)

        c.drawString(x_student, y, s_lines[0][:40])
        c.drawString(x_school, y, school[:28])
        c.drawString(x_class, y, clazz[:10])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

        if len(s_lines) > 1 and s_lines[1].strip():
            if y < 2.4 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
                y = head(y)
            c.drawString(x_student, y, s_lines[1][:40])
            y -= 0.40 * cm

    pdf_footer(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_report_by_class(by_class: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> io.BytesIO:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes, app_url, qr_enabled)

    x_school = left
    x_class = left + 9.0 * cm
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos: float) -> float:
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
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
            y = head(y)
        school = str(r.get("Σχολείο", "") or "")
        clazz = str(r.get("Τάξη", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)
        c.drawString(x_school, y, school[:52])
        c.drawString(x_class, y, clazz[:18])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_report_by_school(by_school: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> io.BytesIO:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes, app_url, qr_enabled)

    x_school = left
    x_qty_r = right - 4.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos: float) -> float:
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_school, ypos, "Σχολείο")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)
    for _, r in by_school.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
            y = head(y)
        school = str(r.get("Σχολείο", "") or "")
        qty = int(float(r.get("ποσότητα", 0) or 0))
        total = float(r.get("σύνολο", 0.0) or 0.0)
        c.drawString(x_school, y, school[:60])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{total:.2f}")
        y -= 0.40 * cm

    pdf_footer(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_report_by_product(by_product: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> io.BytesIO:
    # expects columns: product, qty, total
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes, app_url, qr_enabled)

    x_prod = left
    x_qty_r = right - 3.0 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos: float) -> float:
        c.setFont(FONT_BLD, 9.5)
        c.drawString(x_prod, ypos, "Προϊόν")
        c.drawRightString(x_qty_r, ypos, "Ποσότητα")
        c.drawRightString(x_total_r, ypos, "Σύνολο (€)")
        c.setFont(FONT_REG, 9.5)
        return ypos - 0.55 * cm

    y = head(y)
    for _, r in by_product.iterrows():
        if y < 2.4 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
            y = head(y)
        prod = str(r.get("product", "") or "")
        qty = int(float(r.get("qty", 0) or 0))
        tot = float(r.get("total", 0.0) or 0.0)
        c.drawString(x_prod, y, prod[:64])
        c.drawRightString(x_qty_r, y, f"{qty}")
        c.drawRightString(x_total_r, y, f"{tot:.2f}")
        y -= 0.40 * cm

    pdf_footer(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_bulletin_grouped(detail: pd.DataFrame, title: str, logo_bytes: bytes | None, app_url: str, qr_enabled: bool) -> io.BytesIO:
    """
    Grouped bulletin PDF (School -> Student). Requirements:
    - Student label on 2 lines (label line then name line), no class shown
    - Fixed columns, clean spacing, separator line and blank gap between students
    - 'Τελικό σύνολο' label
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 2 * cm, w - 2 * cm
    y = pdf_header(c, title, logo_bytes, app_url, qr_enabled)

    # table columns
    x_prod = left
    x_price_r = right - 7.0 * cm
    x_qty_r = right - 3.5 * cm
    x_total_r = right - 0.5 * cm

    def head(ypos: float) -> float:
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
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)

        c.setFont(FONT_BLD, 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.70 * cm

        school_total = 0.0

        for student, g_student in g_school.groupby("student", dropna=False):
            if y < 3.2 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)

            # Student block (two lines label/name; wrap name to max 2 lines)
            c.setFont(FONT_BLD, 10.5)
            c.drawString(left, y, "Μαθητής/-τρια:")
            y -= 0.45 * cm

            c.setFont(FONT_REG, 11)
            s_lines = wrap_lines(student, 48, 2)
            c.drawString(left, y, s_lines[0])
            y -= 0.45 * cm
            if len(s_lines) > 1 and s_lines[1].strip():
                c.drawString(left, y, s_lines[1])
                y -= 0.45 * cm

            y = head(y)

            subtotal = 0.0
            c.setFont(FONT_REG, 9.5)

            for _, r in g_student.sort_values(["product"]).iterrows():
                if y < 2.4 * cm:
                    y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
                    y = head(y)

                prod = str(r.get("product", "") or "")
                prod_lines = wrap_lines(prod, 52, 2)
                unit_price = float(r.get("unit_price", 0.0) or 0.0)
                qty = int(float(r.get("qty", 0) or 0))
                tot = float(r.get("total", 0.0) or 0.0)

                c.drawString(x_prod, y, prod_lines[0])
                c.drawRightString(x_price_r, y, f"{unit_price:.2f}")
                c.drawRightString(x_qty_r, y, f"{qty}")
                c.drawRightString(x_total_r, y, f"{tot:.2f}")
                y -= 0.38 * cm

                if len(prod_lines) > 1 and prod_lines[1].strip():
                    if y < 2.4 * cm:
                        y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)
                        y = head(y)
                    c.drawString(x_prod, y, prod_lines[1])
                    y -= 0.38 * cm

                subtotal += tot

            if y < 2.8 * cm:
                y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)

            c.setFont(FONT_BLD, 10.5)
            c.drawRightString(x_total_r, y, f"Τελικό σύνολο: {subtotal:.2f} €")
            y -= 0.45 * cm

            # separator line + extra gap
            c.setLineWidth(0.4)
            c.line(left, y, right, y)
            y -= 0.65 * cm

            school_total += subtotal

        if y < 2.8 * cm:
            y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)

        c.setFont(FONT_BLD, 11.5)
        c.drawRightString(right - 0.5 * cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.85 * cm

        grand_total += school_total

    if y < 2.8 * cm:
        y = pdf_new_page(c, title, logo_bytes, app_url, qr_enabled)

    c.setFont(FONT_BLD, 12.5)
    c.drawRightString(right - 0.5 * cm, y, f"Γενικό Σύνολο: {grand_total:.2f} €")

    pdf_footer(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# =========================
# Session defaults
# =========================
def get_default_logo_bytes() -> bytes | None:
    if REPO_LOGO_PATH.exists():
        try:
            return REPO_LOGO_PATH.read_bytes()
        except Exception:
            return None
    return None


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = get_default_logo_bytes()
if "qr_enabled" not in st.session_state:
    st.session_state["qr_enabled"] = False
if "app_url" not in st.session_state:
    st.session_state["app_url"] = APP_URL_DEFAULT
if "backup_zip_bytes" not in st.session_state:
    st.session_state["backup_zip_bytes"] = None
if "backup_ts" not in st.session_state:
    st.session_state["backup_ts"] = _read_last_backup_ts()
if "my_order_ids" not in st.session_state:
    st.session_state["my_order_ids"] = []


# =========================
# Login gate (Option 2)
# =========================
if not st.session_state["logged_in"]:
    st.markdown(f"## {APP_TITLE}")
    st.info("🔐 Η πρόσβαση στην εφαρμογή προστατεύεται με κωδικό.")
    pwd = st.text_input("Κωδικός πρόσβασης", type="password")
    if st.button("Είσοδος"):
        if str(pwd) == str(APP_PASSWORD):
            st.session_state["logged_in"] = True
            st.success("✅ Επιτυχής είσοδος")
            st.rerun()
        else:
            st.error("Λάθος κωδικός.")
    st.stop()


# =========================
# Sidebar: role & admin controls
# =========================
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

    cbtn1, cbtn2 = st.sidebar.columns(2)
    with cbtn1:
        if st.button("🧹 Καθαρισμός λογοτύπου", key="clear_logo"):
            st.session_state["logo_bytes"] = None
            st.rerun()
    with cbtn2:
        if st.button("↩️ Repo logo", key="reset_logo"):
            st.session_state["logo_bytes"] = get_default_logo_bytes()
            st.rerun()

    st.session_state["app_url"] = st.sidebar.text_input("URL εφαρμογής (για QR)", value=st.session_state["app_url"] or "")
    st.session_state["qr_enabled"] = st.sidebar.toggle("QR στο PDF (ON/OFF)", value=st.session_state["qr_enabled"])

# show logo in sidebar
if st.session_state.get("logo_bytes"):
    st.sidebar.image(st.session_state["logo_bytes"], use_column_width=True)

# Quick backup (admin)
if is_admin:
    st.sidebar.markdown("### Backup δεδομένων")
    st.session_state["backup_ts"] = _read_last_backup_ts()

    if st.sidebar.button("⚡ Γρήγορο backup τώρα", key="quick_backup_btn"):
        b, ts = make_backup_zip()
        st.session_state["backup_zip_bytes"] = b
        st.session_state["backup_ts"] = ts

    if st.session_state.get("backup_zip_bytes"):
        st.sidebar.download_button(
            "⬇️ Λήψη backup ZIP",
            data=st.session_state["backup_zip_bytes"],
            file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",
            key="dl_backup_sidebar",
        )

    if st.session_state.get("backup_ts"):
        try:
            last_dt = datetime.strptime(st.session_state["backup_ts"], "%Y-%m-%d %H:%M:%S")
            days = (datetime.now() - last_dt).days
            if days >= 3:
                st.sidebar.warning(f"⚠️ Συνιστάται νέο backup (τελευταίο: {st.session_state['backup_ts']})")
            else:
                st.sidebar.caption(f"Τελευταίο backup: {st.session_state['backup_ts']}")
        except Exception:
            st.sidebar.caption(f"Τελευταίο backup: {st.session_state['backup_ts']}")


# =========================
# Top bar
# =========================
c_logo, c_title = st.columns([1, 10])
with c_logo:
    if st.session_state.get("logo_bytes"):
        st.image(st.session_state["logo_bytes"], width=72)
with c_title:
    st.markdown(f"## {APP_TITLE}")
    st.caption("Καταχώριση • Διόρθωση/Διαγραφή • Αναφορές • PDF • Backup")


# =========================
# Navigation
# =========================
pages_admin = ["Παραγγελίες", "Σύνοψη", "Δελτία", "Backup / Επαναφορά", "Κατάλογος", "Μαθητές"]
pages_user = ["Παραγγελίες", "Σύνοψη", "Δελτία"]
page = st.sidebar.radio("Μενού", pages_admin if is_admin else pages_user, index=0)


# =========================
# Page renderers
# =========================
def render_catalog() -> None:
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Κατάλογος προϊόντων")
    products = load_products().copy()

    with st.form("add_product"):
        c1, c2 = st.columns([3, 1])
        with c1:
            pname = st.text_input("Προϊόν", placeholder="π.χ. Sandwich")
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

    st.markdown("### Μαζικές διαγραφές")
    if not products.empty:
        multi = st.multiselect("Επίλεξε προϊόντα", products["product"].tolist())
        conf = st.checkbox("✅ Επιβεβαίωση", key="conf_del_prod")
        if st.button("🗑️ Διαγραφή επιλεγμένων") and conf and multi:
            products2 = products[~products["product"].isin(multi)].reset_index(drop=True)
            save_products(products2)
            st.success(f"Διαγράφηκαν {len(multi)} προϊόντα.")
            st.rerun()
    else:
        st.info("Δεν υπάρχουν προϊόντα.")

    st.dataframe(products.rename(columns={"product": "Προϊόν", "price": "Τιμή (€)"}), use_container_width=True)


def render_students() -> None:
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Μαθητές/τριες")
    students = load_students().copy()

    with st.form("add_student"):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            sname = st.text_input("Ονοματεπώνυμο")
        with c2:
            school = st.text_input("Σχολείο")
        with c3:
            clazz = st.text_input("Τάξη")
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

    if not students.empty:
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}", axis=1)
        multi = st.multiselect("Μαζική διαγραφή (επιλογή)", students["label"].tolist())
        conf = st.checkbox("✅ Επιβεβαίωση", key="conf_del_students")
        if st.button("🗑️ Διαγραφή επιλεγμένων") and conf and multi:
            kept = students[~students["label"].isin(multi)][["student", "school", "class"]]
            save_students(kept)
            st.success(f"Διαγράφηκαν {len(multi)} εγγραφές.")
            st.rerun()
    else:
        st.info("Δεν υπάρχουν μαθητές/τριες.")

    st.dataframe(students.rename(columns={"student": "Ονοματεπώνυμο", "school": "Σχολείο", "class": "Τάξη"}), use_container_width=True)


def _init_order_lines() -> None:
    if "order_lines" not in st.session_state:
        st.session_state["order_lines"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})


def _compute_order_view(lines: pd.DataFrame, price_map: dict[str, float]) -> pd.DataFrame:
    df = lines.copy()
    if "Προϊόν" not in df.columns:
        df["Προϊόν"] = ""
    if "Ποσότητα" not in df.columns:
        df["Ποσότητα"] = 1

    df["Προϊόν"] = df["Προϊόν"].astype(str).str.strip()
    df["Ποσότητα"] = pd.to_numeric(df["Ποσότητα"], errors="coerce").fillna(1).astype(int).clip(lower=1)

    df["Τιμή (€)"] = df["Προϊόν"].map(lambda p: float(price_map.get(p, 0.0)))
    df["Μερικό (€)"] = df["Τιμή (€)"] * df["Ποσότητα"]
    return df


def render_orders() -> None:
    st.subheader("Παραγγελίες")

    products = load_products()
    students = load_students()

    if products.empty or students.empty:
        st.info("Χρειάζονται προϊόντα και μαθητές/τριες. Αν είσαι διαχειριστής/ρια, συμπλήρωσέ τα από τις καρτέλες.")
        return

    catalog = products["product"].tolist()
    price_map = dict(zip(products["product"], products["price"]))

    students_local = students.copy()
    sort_mode = st.radio(
        "Ταξινόμηση μαθητών/τριών",
        ["Αλφαβητικά", "Ανά σχολείο → τάξη → αλφαβητικά", "Ανά τάξη → αλφαβητικά"],
        horizontal=True,
        index=1,
    )
    if sort_mode == "Αλφαβητικά":
        students_local = students_local.sort_values(["student", "school", "class"], na_position="last")
    elif sort_mode == "Ανά τάξη → αλφαβητικά":
        students_local = students_local.sort_values(["class", "student", "school"], na_position="last")
    else:
        students_local = students_local.sort_values(["school", "class", "student"], na_position="last")
    students_local["label"] = students_local.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}", axis=1)

    tabs = st.tabs(["🆕 Νέα παραγγελία", "✏️ Διόρθωση / Διαγραφή"])

    # ---------- New order ----------
    with tabs[0]:
        c1, c2 = st.columns([1.2, 3])
        with c1:
            d = st.date_input("Ημερομηνία", value=date.today())
        with c2:
            label = st.selectbox("Μαθητής/-τρια", students_local["label"].tolist(), key="order_student_label")

        sel = students_local.loc[students_local["label"] == label].iloc[0]
        s_name, s_school, s_class = sel["student"], sel["school"], sel["class"]

        _init_order_lines()

        # Reset lines when student changes (optional, safer workflow)
        if st.session_state.get("last_student_label") != label:
            st.session_state["order_lines"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})
            st.session_state["last_student_label"] = label

        view_df = _compute_order_view(st.session_state["order_lines"], price_map)
        subtotal = float(view_df["Μερικό (€)"].sum()) if not view_df.empty else 0.0

        # Live editor (no form) so totals appear immediately
        edited = st.data_editor(
            view_df[["Προϊόν", "Ποσότητα", "Τιμή (€)", "Μερικό (€)"]],
            key="order_editor_live",
            num_rows="dynamic",
            column_config={
                "Προϊόν": st.column_config.SelectboxColumn("Προϊόν", options=catalog, required=False),
                "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1),
                "Τιμή (€)": st.column_config.NumberColumn("Τιμή (€)", format="%.2f", disabled=True),
                "Μερικό (€)": st.column_config.NumberColumn("Μερικό (€)", format="%.2f", disabled=True),
            },
            use_container_width=True,
        )

        # Persist only editable cols back to session_state
        st.session_state["order_lines"] = edited[["Προϊόν", "Ποσότητα"]].copy()

        # Recompute after edit (so subtotal reflects latest state)
        view_df = _compute_order_view(st.session_state["order_lines"], price_map)
        subtotal = float(view_df["Μερικό (€)"].sum()) if not view_df.empty else 0.0
        st.markdown(f"**Σύνολο τρέχουσας παραγγελίας:** {subtotal:.2f} €")

        b1, b2, b3 = st.columns([1, 1, 2])
        with b1:
            save_click = st.button("✅ Καταχώριση παραγγελίας", use_container_width=True)
        with b2:
            new_click = st.button("🧹 Νέα παραγγελία", use_container_width=True)
        with b3:
            add_row = st.button("➕ Προσθήκη γραμμής", use_container_width=True)

        if add_row:
            tmp = st.session_state["order_lines"].copy()
            tmp = pd.concat([tmp, pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})], ignore_index=True)
            st.session_state["order_lines"] = tmp
            st.rerun()

        if new_click:
            st.session_state["order_lines"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})
            st.rerun()

        if save_click:
            df_save = _compute_order_view(st.session_state["order_lines"], price_map)
            df_save = df_save[df_save["Προϊόν"].isin(catalog) & (df_save["Προϊόν"].str.len() > 0)].copy()
            if df_save.empty:
                st.warning("Δεν βρέθηκαν έγκυρες γραμμές προϊόντων για αποθήκευση.")
            else:
                rows = []
                new_ids = []
                for _, r in df_save.iterrows():
                    oid = str(uuid.uuid4())
                    qty = int(r["Ποσότητα"])
                    unit_price = float(r["Τιμή (€)"])
                    total = float(r["Μερικό (€)"])
                    rows.append({
                        "order_id": oid,
                        "date": pd.to_datetime(d),
                        "student": s_name,
                        "school": s_school,
                        "class": s_class,
                        "product": str(r["Προϊόν"]),
                        "qty": qty,
                        "unit_price": unit_price,
                        "total": total,
                    })
                    new_ids.append(oid)

                all_orders = load_orders().copy()
                all_orders = pd.concat([all_orders, pd.DataFrame(rows)], ignore_index=True)
                save_orders(all_orders)

                st.session_state["my_order_ids"].extend(new_ids)
                st.session_state["order_lines"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})
                st.success("✅ Η παραγγελία αποθηκεύτηκε.")
                st.rerun()

    # ---------- Edit/Delete ----------
    with tabs[1]:
        orders = load_orders().copy()
        if orders.empty:
            st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
            return

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

        student_list = sorted(df["student"].dropna().unique().tolist())
        sel_student = st.selectbox("Μαθητής/-τρια (προβολή όλων των ειδών)", ["(επιλογή...)"] + student_list)
        if sel_student == "(επιλογή...)":
            return

        df_s = df[df["student"] == sel_student].copy().sort_values(["date", "product"])
        st.markdown(f"**Σύνολο μαθητή/-τριας:** {df_s['total'].sum():.2f} €")

        view = df_s.copy()
        view["Ημερομηνία"] = pd.to_datetime(view["date"], errors="coerce").dt.date
        view = view.rename(columns={
            "school": "Σχολείο",
            "class": "Τάξη",
            "product": "Προϊόν",
            "qty": "Ποσότητα",
            "unit_price": "Τιμή (€)",
            "total": "Σύνολο (€)",
        })
        view = view[["Ημερομηνία", "Σχολείο", "Τάξη", "Προϊόν", "Ποσότητα", "Τιμή (€)", "Σύνολο (€)", "order_id"]]

        editor = st.data_editor(
            view.drop(columns=["order_id"]),
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
                    oids = view["order_id"].tolist()
                    ed = editor.copy()
                    ed["Ποσότητα"] = pd.to_numeric(ed["Ποσότητα"], errors="coerce").fillna(1).astype(int).clip(lower=1)
                    ed["Τιμή (€)"] = pd.to_numeric(ed["Τιμή (€)"], errors="coerce").fillna(0.0).clip(lower=0.0)
                    ed["Σύνολο (€)"] = ed["Ποσότητα"] * ed["Τιμή (€)"]

                    all_orders = load_orders().copy()
                    for i, oid in enumerate(oids):
                        rowi = ed.iloc[i]
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
            labels = view.apply(lambda r: f"{r['Ημερομηνία']} • {r['Προϊόν']} (qty {int(r['Ποσότητα'])})", axis=1).tolist()
            del_sel = st.multiselect("Διαγραφή γραμμών", labels)
            conf = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="conf_del_lines")
            if st.button("🗑️ Διαγραφή επιλεγμένων") and conf and del_sel:
                del_oids = [view.iloc[i]["order_id"] for i, lab in enumerate(labels) if lab in del_sel]
                all_orders = load_orders().copy()
                all_orders = all_orders[~all_orders["order_id"].isin(del_oids)]
                save_orders(all_orders)
                if not is_admin:
                    st.session_state["my_order_ids"] = [x for x in st.session_state.get("my_order_ids", []) if x not in del_oids]
                st.success(f"Διαγράφηκαν {len(del_oids)} γραμμές.")
                st.rerun()


def render_summary() -> None:
    st.subheader("Σύνοψη & Αναφορές")
    orders = load_orders().copy()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
        return

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
    )

    st.markdown("### Ανά μαθητή/-τρια")
    st.dataframe(by_student, use_container_width=True)

    st.markdown("### Ανά τάξη")
    st.dataframe(by_class, use_container_width=True)

    st.markdown("### Ανά σχολείο")
    st.dataframe(by_school, use_container_width=True)

    st.markdown("### Ανά προϊόν (για κατάστημα)")
    st.dataframe(by_product.rename(columns={"product": "Προϊόν", "qty": "Ποσότητα", "total": "Σύνολο (€)"}), use_container_width=True)

    st.divider()
    st.markdown("### Excel αναφορές")

    excel_bytes = dfs_to_xlsx_bytes({
        "Ανά μαθητή": by_student,
        "Ανά τάξη": by_class,
        "Ανά σχολείο": by_school,
        "Ανά προϊόν": by_product.rename(columns={"product": "Προϊόν", "qty": "Ποσότητα", "total": "Σύνολο (€)"}),
    })

    st.download_button(
        "⬇️ Λήψη Excel (όλες οι αναφορές)",
        data=excel_bytes,
        file_name=f"αναφορές_{d_from}_{d_to}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_excel_all_reports",
    )


    # PDF buttons
    st.divider()
    st.markdown("### PDF αναφορές (fixed, minimal)")
    p1, p2, p3, p4 = st.columns(4)
    with p1:
        if st.button("📄 PDF: Ανά μαθητή"):
            pdfbuf = pdf_report_by_student(by_student, "Αναφορά ανά μαθητή/τρια", st.session_state.get("logo_bytes"),
                                           st.session_state.get("app_url",""), st.session_state.get("qr_enabled", False))
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_μαθητη.pdf", mime="application/pdf")
    with p2:
        if st.button("📄 PDF: Ανά τάξη"):
            pdfbuf = pdf_report_by_class(by_class, "Αναφορά ανά τάξη", st.session_state.get("logo_bytes"),
                                         st.session_state.get("app_url",""), st.session_state.get("qr_enabled", False))
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_ταξη.pdf", mime="application/pdf")
    with p3:
        if st.button("📄 PDF: Ανά σχολείο"):
            pdfbuf = pdf_report_by_school(by_school, "Αναφορά ανά σχολείο", st.session_state.get("logo_bytes"),
                                          st.session_state.get("app_url",""), st.session_state.get("qr_enabled", False))
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_σχολειο.pdf", mime="application/pdf")
    with p4:
        if st.button("📄 PDF: Ανά προϊόν"):
            pdfsrc = by_product.rename(columns={"product": "product", "qty": "qty", "total": "total"})
            pdfbuf = pdf_report_by_product(pdfsrc, "Παραγγελία προς κατάστημα", st.session_state.get("logo_bytes"),
                                           st.session_state.get("app_url",""), st.session_state.get("qr_enabled", False))
            st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_καταστημα.pdf", mime="application/pdf")


def render_bulletins() -> None:
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
        df.groupby(["student", "school", "product", "unit_price"], as_index=False)
        .agg(qty=("qty", "sum"), total=("total", "sum"))
        .sort_values(["school", "student", "product"])
    )

    st.dataframe(
        detail.rename(columns={
            "student": "Μαθητής/-τρια",
            "school": "Σχολείο",
            "product": "Προϊόν",
            "unit_price": "Τιμή (€)",
            "qty": "Ποσότητα",
            "total": "Σύνολο (€)",
        }),
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Λήψη Excel (δελτίο – όπως φαίνεται)",
        data=dfs_to_xlsx_bytes({
            "Δελτίο": detail.rename(columns={
                "student": "Μαθητής/-τρια",
                "school": "Σχολείο",
                "product": "Προϊόν",
                "unit_price": "Τιμή (€)",
                "qty": "Ποσότητα",
                "total": "Σύνολο (€)",
            })
        }),
        file_name=f"δελτίο_{d_from}_{d_to}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_excel_bulletin",
    )


    if st.button("📄 Εξαγωγή PDF (ομαδοποίηση ανά σχολείο/μαθητή)"):
        pdfbuf = pdf_bulletin_grouped(detail, "Δελτίο Παραγγελιών", st.session_state.get("logo_bytes"),
                                      st.session_state.get("app_url",""), st.session_state.get("qr_enabled", False))
        st.download_button("⬇️ Λήψη PDF", data=pdfbuf.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")


def render_backup() -> None:
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()

    st.subheader("Backup / Επαναφορά")
    st.write("Δημιούργησε αντίγραφο ασφαλείας (ZIP) ή επανάφερε δεδομένα από backup.")

    st.markdown("### Δημιουργία backup")
    b1, b2 = st.columns([1, 2])
    with b1:
        if st.button("✅ Δημιουργία backup ZIP", key="make_backup_page"):
            b, ts = make_backup_zip()
            st.session_state["backup_zip_bytes"] = b
            st.session_state["backup_ts"] = ts
    with b2:
        if st.session_state.get("backup_ts"):
            st.info(f"Τελευταίο backup: {st.session_state['backup_ts']}")

    if st.session_state.get("backup_zip_bytes"):
        st.download_button(
            "⬇️ Λήψη backup ZIP",
            data=st.session_state["backup_zip_bytes"],
            file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",
            key="dl_backup_page",
        )

    st.divider()
    st.markdown("### Επαναφορά από backup ZIP")
    up = st.file_uploader("Ανέβασε backup ZIP", type=["zip"], key="up_restore_zip")
    confirm = st.checkbox("✅ Επιβεβαιώνω ότι η επαναφορά θα αντικαταστήσει τα τρέχοντα δεδομένα", key="conf_restore_zip")
    if up is not None and confirm:
        if st.button("↩️ Εκτέλεση επαναφοράς", key="do_restore_zip"):
            try:
                msg = restore_backup_zip(up.read())
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα επαναφοράς: {e}")


# =========================
# Dispatch
# =========================
if page == "Παραγγελίες":
    render_orders()
elif page == "Σύνοψη":
    render_summary()
elif page == "Δελτία":
    render_bulletins()
elif page == "Backup / Επαναφορά":
    render_backup()
elif page == "Κατάλογος":
    render_catalog()
elif page == "Μαθητές":
    render_students()
else:
    st.error("Άγνωστη σελίδα.")
