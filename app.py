
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
    load_products.clear()

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
    load_students.clear()

def save_orders(df):
    cols = ["order_id","date","student","school","class","product","qty","unit_price","total"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[cols]
    df.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    load_orders.clear()

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
                c.drawRightString(right-6.5*cm, y, f"{row['unit_price']:.2f}")
                c.drawRightString(right-3.5*cm, y, f"{int(row['qty']) if pd.notna(row['qty']) else ''}")
                c.drawRightString(right-0.5*cm, y, f"{row['total']:.2f}")
                y -= 0.35*cm
                subtotal += float(row["total"] or 0)

            if y < 2*cm: y = _paginate_new_page(c, title, app_url)
            c.setFont(FONT_BLD, 10)
            c.drawRightString(right-0.5*cm, y, f"Σύνολο {student}: {subtotal:.2f} €")
            y -= 0.5*cm
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
        c.drawRightString(right-0.5*cm, y, f"{row['total']:.2f}")
        y -= 0.4*cm

    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def pdf_table(df, title="Αναφορά", columns=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 2*cm
    right = width - 2*cm

    y = _draw_header_with_logo(c, title)
    cols = columns or [(col, col, "L") for col in df.columns]
    c.setFont(FONT_BLD, 9)
    step = (right-left) / len(cols)
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
            if align == "R":
                c.drawRightString(left + (i+1)*step - 2, y, s[:22])
            else:
                c.drawString(left + i*step, y, s[:26])
        y -= 0.38*cm

    _draw_footer(c, c.getPageNumber(), app_url)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ---- UI
show_topbar()

pages = ["Κατάλογος", "Μαθητές", "Παραγγελίες", "Σύνοψη", "Δελτία", "Διαχείριση"]
if not is_admin:
    pages = ["Παραγγελίες", "Σύνοψη"]
page = st.sidebar.radio("Μενού", pages, index=0)

# --- Κατάλογος (Admin)
if page == "Κατάλογος":
    if not is_admin:
        st.error("Μόνο διαχειριστής/ρια.")
        st.stop()
    st.subheader("Τιμοκατάλογος")
    products = load_products().copy()

    with st.form("add_product"):
        cols = st.columns([3,1,1])
        with cols[0]:
            p = st.text_input("Προϊόν", placeholder="π.χ. Club sandwich")
        with cols[1]:
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
    uplp = st.file_uploader("Επιλογή αρχείου Excel προϊόντων", type=["xlsx"], key="prod_excel")
    if uplp is not None:
        try:
            xl = pd.ExcelFile(uplp)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                lower = {str(c).strip(): str(c).strip().lower() for c in df.columns}
                df = df.rename(columns=lower)
                if "προϊόν" in df.columns and "τιμή" in df.columns:
                    tmp = df.rename(columns={"προϊόν":"product","τιμή":"price"})[["product","price"]]
                elif "product" in df.columns and "price" in df.columns:
                    tmp = df[["product","price"]]
                else:
                    tmp = df.iloc[:, :2].copy()
                    tmp.columns = ["product","price"]
                frames.append(tmp)
            merged = pd.concat(frames, ignore_index=True)
            merged["product"] = merged["product"].astype(str).str.strip()
            merged["price"] = pd.to_numeric(merged["price"], errors="coerce").fillna(0.0)
            save_products(pd.concat([products, merged], ignore_index=True))
            st.success("Ο τιμοκατάλογος ενημερώθηκε από το Excel.")
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
        multi_del = st.multiselect("Μαζική διαγραφή προϊόντων", products["product"].tolist(), key="del_prod_multi")
        confirm_multi = st.checkbox("✅ Επιβεβαίωση μαζικής", key="confirm_prod_multi")
        if st.button("🗑️ Διαγραφή επιλεγμένων") and multi_del and confirm_multi:
            products = products[~products["product"].isin(multi_del)].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκαν: {', '.join(multi_del)}")
            st.rerun()

    st.markdown("#### Λίστα προϊόντων")
    st.dataframe(products.rename(columns={"product":"Προϊόν","price":"Τιμή (€)"}), use_container_width=True)

# --- Μαθητές (Admin)
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
        exists = ((students["student"].str.lower()==s.strip().lower()) & (students["school"].str.lower()==sch.strip().lower()) & (students["class"].str.lower()==cl.strip().lower())).any()
        if exists:
            st.warning("Υπάρχει ήδη.")
        else:
            students.loc[len(students)] = [s.strip(), sch.strip(), cl.strip()]
            save_students(students)
            st.success("Προστέθηκε.")
            st.rerun()

    st.markdown("**Ανέβασμα Excel: Ονοματεπώνυμο – Σχολείο – Τάξη**")
    upl = st.file_uploader("Επιλογή αρχείου Excel", type=["xlsx"])
    if upl is not None:
        try:
            xl = pd.ExcelFile(upl)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                lower = {str(c).strip(): str(c).strip().lower() for c in df.columns}
                df = df.rename(columns=lower)
                if "ονοματεπώνυμο" in df.columns:
                    if "σχολείο" not in df.columns:
                        df["σχολείο"] = ""
                    if "τάξη" not in df.columns:
                        df["τάξη"] = ""
                    tmp = df.rename(columns={"ονοματεπώνυμο":"student","σχολείο":"school","τάξη":"class"})[["student","school","class"]]
                elif "student" in df.columns:
                    if "school" not in df.columns:
                        df["school"] = ""
                    if "class" not in df.columns:
                        df["class"] = ""
                    tmp = df[["student","school","class"]]
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
            merged = pd.concat(frames, ignore_index=True)
            save_students(pd.concat([students, merged], ignore_index=True))
            st.success("Οι μαθητές ενημερώθηκαν από το Excel.")
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

    st.markdown("#### Τρέχουσα λίστα")
    st.dataframe(load_students().rename(columns={"student":"Ονοματεπώνυμο","school":"Σχολείο","class":"Τάξη"}), use_container_width=True)

# --- Παραγγελίες και κάτω συνεχίζει...
