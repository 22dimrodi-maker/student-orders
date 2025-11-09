
import streamlit as st
import pandas as pd
import io, uuid, os
from pathlib import Path
from datetime import date, datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.graphics.barcode import qr
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register clean fonts for PDF (less "black" than Helvetica)
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    FONT_REG = "DejaVuSans"
    FONT_BLD = "DejaVuSans-Bold"
except Exception:
    FONT_REG = "Helvetica"
    FONT_BLD = "Helvetica-Bold"

st.set_page_config(page_title="Παραγγελίες Μαθητών", layout="wide")

# ---- Paths & Config
DATA_DIR = Path(".")
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
ORDERS_PATH = DATA_DIR / "orders.csv"
DEFAULT_LOGO = Path("/mnt/data/logo (2).png")
APP_URL = st.secrets.get("APP_URL", os.getenv("APP_URL", "https://your-app-url-here"))

# ---- Role / Auth
ADMIN_PIN = st.secrets.get("ADMIN_PIN", os.getenv("ADMIN_PIN", "1234"))
role = st.sidebar.selectbox("Ρόλος", ["Καταχώριση", "Διαχειριστής"], index=0)
is_admin = False
if role == "Διαχειριστής":
    pin = st.sidebar.text_input("PIN Διαχειριστή", type="password")
    if pin == str(ADMIN_PIN):
        is_admin = True
        st.sidebar.success("✅ Διαχειριστής/ρια")
    else:
        st.sidebar.warning("Πληκτρολόγησε σωστό PIN για λειτουργίες διαχείρισης.")

# ---- Logo controls (κρυφά για Καταχώριση)
st.sidebar.markdown("### Ρυθμίσεις εμφάνισης")
if "logo_bytes" not in st.session_state:
    if DEFAULT_LOGO.exists():
        st.session_state["logo_bytes"] = DEFAULT_LOGO.read_bytes()
    else:
        st.session_state["logo_bytes"] = None

if is_admin:
    st.sidebar.markdown("#### Λογότυπο & URL για QR")
    logo_file = st.sidebar.file_uploader("Ανέβασμα λογοτύπου (PNG/JPG)", type=["png","jpg","jpeg"], key="logo_up")
    if logo_file is not None:
        st.session_state["logo_bytes"] = logo_file.read()
    app_url = st.sidebar.text_input("URL εφαρμογής (για QR)", APP_URL)
    if st.session_state.get("logo_bytes"):
        st.sidebar.image(st.session_state["logo_bytes"], caption="Λογότυπο", use_column_width=True)
else:
    app_url = APP_URL

# --- Top UI bar with logo preview (μόνο προβολή)
def show_topbar():
    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        if st.session_state.get("logo_bytes"):
            st.image(st.session_state["logo_bytes"], width=64, caption=None)
    with col_title:
        st.markdown("## 🍔 Παραγγελίες Μαθητών")
        st.caption("Μαθητές από πολλά σχολεία, παραγγελίες, PDF δελτία, αναφορές & εξαγωγές.")

# ---- Loaders / Savers
@st.cache_data
def load_products():
    if PRODUCTS_PATH.exists():
        df = pd.read_csv(PRODUCTS_PATH)
    else:
        df = pd.DataFrame(columns=["product","price"])
    df["product"] = df.get("product","").astype(str).str.strip()
    df["price"] = pd.to_numeric(df.get("price", 0), errors="coerce").fillna(0.0)
    return df

@st.cache_data
def load_students():
    if STUDENTS_PATH.exists():
        df = pd.read_csv(STUDENTS_PATH)
    else:
        df = pd.DataFrame(columns=["student","school","class"])
    for c in ["student","school","class"]:
        if c not in df.columns:
            df[c] = ""
    df["student"] = df["student"].astype(str).str.strip()
    df["school"] = df["school"].astype(str).str.strip()
    df["class"] = df["class"].astype(str).str.strip()
    return df

@st.cache_data

def seed_demo_data():
    """Create minimal demo data if products/students CSVs are empty/missing."""
    prods = load_products()
    studs = load_students()
    changed = False
    if prods.empty:
        prods = pd.DataFrame([{"product":"Τοστ","price":2.0},{"product":"Χυμός","price":1.5}])
        prods.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
        load_products.clear() if hasattr(load_products, 'clear') else None
        changed = True
    if studs.empty:
        studs = pd.DataFrame([{"student":"Δείγμα Μαθητή/τρια","school":"Δείγμα Σχολείο","class":"Α1"}])
        studs.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
        load_students.clear() if hasattr(load_students, 'clear') else None
        changed = True
    return changed

def load_orders():
    if ORDERS_PATH.exists():
        df = pd.read_csv(ORDERS_PATH, parse_dates=["date"])
    else:
        df = pd.DataFrame(columns=["order_id","date","student","school","class","product","qty","unit_price","total"])
    if "order_id" not in df.columns:
        df["order_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    for c in ["date","student","school","class","product","qty","unit_price","total","order_id"]:
        if c not in df.columns:
            df[c] = pd.NA
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["qty","unit_price","total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["student","school","class","product","order_id"]:
        df[c] = df[c].astype(str).str.strip()
    return df

def save_products(df):
    df = df[["product","price"]].copy()
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df.dropna().drop_duplicates(subset=["product"]).sort_values("product")
    df.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    load_products.clear() if hasattr(load_products, 'clear') else None

def save_students(df):
    for c in ["student","school","class"]:
        if c not in df.columns:
            df[c] = ""
    df = df[["student","school","class"]].dropna().copy()
    df["student"] = df["student"].astype(str).str.strip()
    df["school"] = df["school"].astype(str).str.strip()
    df["class"] = df["class"].astype(str).str.strip()
    df = df.loc[df["student"].str.len() > 0]
    df = df.drop_duplicates(subset=["student","school","class"]).sort_values(["school","class","student"])
    df.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    load_students.clear() if hasattr(load_students, 'clear') else None

def save_orders(df):
    cols = ["order_id","date","student","school","class","product","qty","unit_price","total"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[cols]
    df.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    load_orders.clear() if hasattr(load_orders, 'clear') else None

def to_excel_download(df_dict, filename="report.xlsx", label="⬇️ Λήψη Excel"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        for sheet, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return st.download_button(label, data=output.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- PDF helpers (logo, footer with date/page/QR) using DejaVuSans
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
            y -= 0.5*cm
            c.setFont(FONT_REG, 9)
            school_total += subtotal


    # ----- TAB: Διόρθωση / Διαγραφή
    with tabs[1]:
        st.subheader("Διόρθωση / Διαγραφή")
        st.caption(f"📦 Προϊόντα: {len(load_products())} • 👩‍🎓 Μαθητές: {len(load_students())}")
        products = load_products()
        students = load_students()
        orders = load_orders().copy()

        # για μη admin, δείχνουμε μόνο δικές του (τρέχουσα συνεδρία)
        if not is_admin:
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
                    new_qty = st.number_input("Ποσότητα", min_value=1, step=1, value=int(row["qty"]) if pd.notna(row["qty"]) else 1)
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

# --- Δελτία (PDF grouped ανά σχολείο/μαθητή)
elif page == "Δελτία":
    st.subheader("Δελτίο & Εκτύπωση PDF")
    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
        # Date range
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

        to_excel_download({
            "Δελτίο αναλυτικό": detail
        }, filename="δελτιο.xlsx")

        if st.button("📄 Εξαγωγή PDF (ομαδοποιημένο ανά σχολείο/μαθητή)"):
            buffer = pdf_grouped_by_school_student(detail, title="Δελτίο Παραγγελιών")
            st.download_button("⬇️ Λήψη PDF", data=buffer.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")

# --- Σύνοψη
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
            γραμμές=("order_id", "count"),
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

        to_excel_download({
            "Ανά μαθητή": by_student,
            "Ανά τάξη": by_class,
            "Ανά σχολείο": by_school,
            "Ανά προϊόν": by_product,
            "Αναλυτικά": df.sort_values(["school","class","student","date"]).rename(columns={
                "date":"Ημερομηνία","student":"Μαθητής/-τριες","school":"Σχολείο","class":"Τάξη",
                "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)","total":"Σύνολο (€)"
            })
        }, filename="αναφορές.xlsx")

        colp1, colp2, colp3, colp4 = st.columns(4)
        with colp1:
            if st.button("📄 PDF: Ανά μαθητή"):
                pdfbuf = pdf_table(by_student, title="Αναφορά ανά μαθητή/τρια", columns=[
                    ("Μαθητής/-τριες","Μαθητής/-τριες","L"),
                    ("Σχολείο","Σχολείο","L"),
                    ("Τάξη","Τάξη","L"),
                    ("γραμμές","Γραμμές","R"),
                    ("ποσότητα","Ποσότητα","R"),
                    ("σύνολο","Σύνολο (€)","R"),
                ])
                st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_μαθητη.pdf", mime="application/pdf")
        with colp2:
            if st.button("📄 PDF: Ανά τάξη"):
                pdfbuf = pdf_table(by_class, title="Αναφορά ανά τάξη", columns=[
                    ("Σχολείο","Σχολείο","L"),
                    ("Τάξη","Τάξη","L"),
                    ("παραγγελίες","Παραγγελίες","R"),
                    ("ποσότητα","Ποσότητα","R"),
                    ("σύνολο","Σύνολο (€)","R"),
                ])
                st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_ταξη.pdf", mime="application/pdf")
        with colp3:
            if st.button("📄 PDF: Ανά σχολείο"):
                pdfbuf = pdf_table(by_school, title="Αναφορά ανά σχολείο", columns=[
                    ("Σχολείο","Σχολείο","L"),
                    ("παραγγελίες","Παραγγελίες","R"),
                    ("ποσότητα","Ποσότητα","R"),
                    ("σύνολο","Σύνολο (€)","R"),
                ])
                st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="ανα_σχολειο.pdf", mime="application/pdf")
        with colp4:
            if st.button("📄 PDF: Ανά προϊόν"):
                src = by_product.rename(columns={"Προϊόν":"product","Ποσότητα":"qty","Σύνολο (€)":"total"})
                pdfbuf = pdf_products_report(src, title="Παραγγελία προς κατάστημα")
                st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_κατάστημα.pdf", mime="application/pdf")
