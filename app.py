
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
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))


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

# ---- Logo controls (ΜΟΝΟ για Διαχειριστή)
st.sidebar.markdown("### Ρυθμίσεις εμφάνισης")
if is_admin:
    st.sidebar.markdown("#### Λογότυπο & URL για QR")
    logo_file = st.sidebar.file_uploader("Ανέβασμα λογοτύπου (PNG/JPG)", type=["png","jpg","jpeg"], key="logo_up")
    if "logo_bytes" not in st.session_state:
        if DEFAULT_LOGO.exists():
            st.session_state["logo_bytes"] = DEFAULT_LOGO.read_bytes()
        else:
            st.session_state["logo_bytes"] = None
    if logo_file is not None:
        st.session_state["logo_bytes"] = logo_file.read()
    app_url = st.sidebar.text_input("URL εφαρμογής (για QR)", st.secrets.get("APP_URL", os.getenv("APP_URL", "https://your-app-url-here")))
    if st.session_state.get("logo_bytes"):
        st.sidebar.image(st.session_state["logo_bytes"], caption="Λογότυπο", use_column_width=True)
else:
    app_url = st.secrets.get("APP_URL", os.getenv("APP_URL", "https://your-app-url-here"))

# --- Top UI bar with logo preview (προβολή μόνο)
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

# ---- PDF helpers (logo, footer with date/page/QR)
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
    c.setFont("DejaVuSans-Bold", 14)
    c.drawString(title_x, top, title)
    c.setFont("DejaVuSans", 9)
    c.drawRightString(right, top, f"Ημερομηνία εξαγωγής: {pd.Timestamp.today().date()}")
    return top - 0.8*cm

def _draw_footer(c, page_num, app_url):
    width, _ = A4
    left = 2*cm
    right = width - 2*cm
    bottom = 1.5*cm
    c.setFont("DejaVuSans", 8)
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
        c.setFont("DejaVuSans-Bold", 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.6*cm

        school_total = 0.0
        for student, g2 in g1.groupby("student"):
            if y < 3*cm: y = _paginate_new_page(c, title, app_url)
            c.setFont("DejaVuSans-Bold", 11)
            cls = (g2["class"].iloc[0] or "").strip()
            suffix = f" — Τάξη: {cls}" if cls else ""
            c.drawString(left, y, f"Μαθητής/-τρια: {student}{suffix}")
            y -= 0.5*cm

            c.setFont("DejaVuSans-Bold", 9)
            c.drawString(left, y, "Προϊόν")
            c.drawRightString(right-6.5*cm, y, "Τιμή (€)")
            c.drawRightString(right-3.5*cm, y, "Ποσότητα")
            c.drawRightString(right-0.5*cm, y, "Σύνολο (€)")
            y -= 0.4*cm
            c.setFont("DejaVuSans", 9)

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
            c.setFont("DejaVuSans-Bold", 10)
            c.drawRightString(right-0.5*cm, y, f"Σύνολο {student}: {subtotal:.2f} €")
            y -= 0.5*cm
            c.setFont("DejaVuSans", 9)
            school_total += subtotal

        if y < 2*cm: y = _paginate_new_page(c, title, app_url)
        c.setFont("DejaVuSans-Bold", 11)
        c.drawRightString(right-0.5*cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.7*cm
        grand_total += school_total

    if y < 2*cm: y = _paginate_new_page(c, title, app_url)
    c.setFont("DejaVuSans-Bold", 12)
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
    c.setFont("DejaVuSans-Bold", 10)
    c.drawString(left, y, "Προϊόν")
    c.drawRightString(right-3*cm, y, "Σύνολο Ποσότητας")
    c.drawRightString(right-0.5*cm, y, "Σύνολο (€)")
    y -= 0.5*cm

    for _, row in df.iterrows():
        if y < 2*cm: y = _paginate_new_page(c, title, app_url)
        c.setFont("DejaVuSans", 10)
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
    c.setFont("DejaVuSans-Bold", 9)
    step = (right-left) / len(cols)
    for i, (_c, head, _a) in enumerate(cols):
        c.drawString(left + i*step, y, str(head)[:22])
    y -= 0.45*cm
    c.setFont("DejaVuSans", 9)

    for _, row in df.iterrows():
        if y < 2*cm:
            y = _paginate_new_page(c, title, app_url)
            c.setFont("DejaVuSans-Bold", 9)
            for i, (_c, head, _a) in enumerate(cols):
                c.drawString(left + i*step, y, str(head)[:22])
            y -= 0.45*cm
            c.setFont("DejaVuSans", 9)
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

# --- Παραγγελίες (με tabs Νέα/Διόρθωση)
elif page == "Παραγγελίες":
    products = load_products()
    students = load_students()
    orders = load_orders().copy()

    tabs = st.tabs(["🆕 Νέα παραγγελία", "✏️ Διόρθωση / Διαγραφή"])

    # ----- TAB: Νέα παραγγελία
    with tabs[0]:
        st.subheader("Καταχώριση")
        if students.empty or products.empty:
            st.info("Πρέπει να υπάρχουν μαθητές/τριες και προϊόντα.")
        else:
            students = students.copy()
            students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
            c1, c2, c3 = st.columns([1.2,2,1])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today(), key="order_date")
            with c2:
                label = st.selectbox("Μαθητής/-τρια", students["label"].tolist(), key="order_student")
            with c3:
                if st.button("🧹 Νέα (καθαρισμός)"):
                    st.session_state.pop("order_editor_df", None)
                    st.rerun()

            # Editor: πολλές γραμμές
            catalog = products["product"].tolist()
            if "order_editor_df" not in st.session_state:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})
            edited = st.data_editor(
                st.session_state["order_editor_df"],
                key="order_editor",
                num_rows="dynamic",
                column_config={
                    "Προϊόν": st.column_config.SelectboxColumn("Προϊόν", options=catalog, required=False),
                    "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", min_value=1, step=1)
                },
                use_container_width=True
            )
            st.session_state["order_editor_df"] = edited

            # Υπολογισμός συνόλου παραγγελίας & συνόλου μαθητή (σήμερα)
            row = students.loc[students["label"]==label].iloc[0]
            s, sch, cl = row["student"], row["school"], row["class"]
            # σύνολο τρέχουσας φόρμας
            subtotal = 0.0
            for _, r in edited.dropna(subset=["Προϊόν"]).iterrows():
                p = str(r["Προϊόν"]).strip()
                if not p: continue
                qty = int(r.get("Ποσότητα", 1) or 1)
                unit_price = float(products.loc[products["product"]==p, "price"].iloc[0]) if (products["product"]==p).any() else 0.0
                subtotal += unit_price * qty

            # σύνολο μαθητή στην ημερομηνία
            today_total = orders[(orders["student"]==s) & (orders["date"].dt.date==d)].total.sum() if "total" in orders.columns else 0.0

            st.markdown(f"**Σύνολο τρέχουσας παραγγελίας:** {subtotal:.2f} €")
            st.caption(f"Σύνολο μαθητή για την {d}: {float(today_total):.2f} €")

            cbtn1, cbtn2 = st.columns([1,1])
            with cbtn1:
                save_click = st.button("✅ Καταχώριση παραγγελίας")
            with cbtn2:
                clear_click = st.button("🔁 Νέα παραγγελία")

            if save_click:
                new_rows = []
                new_ids = []
                for _, r in edited.dropna(subset=["Προϊόν"]).iterrows():
                    p = str(r["Προϊόν"]).strip()
                    if not p: 
                        continue
                    qty = int(r.get("Ποσότητα", 1) or 1)
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
                if new_rows:
                    orders = pd.concat([orders, pd.DataFrame(new_rows)], ignore_index=True)
                    save_orders(orders)
                    st.session_state.setdefault("my_last_orders", [])
                    st.session_state["my_last_orders"].extend(new_ids)
                    st.success(f"Καταχωρήθηκαν {len(new_rows)} γραμμές ({subtotal:.2f} €).")
                    st.rerun()
                else:
                    st.warning("Δεν επιλέχθηκαν προϊόντα.")

            if clear_click:
                st.session_state["order_editor_df"] = pd.DataFrame({"Προϊόν": [""], "Ποσότητα": [1]})
                st.experimental_rerun()

            st.divider()
            st.markdown("#### Δικές μου πρόσφατες καταχωρήσεις (αυτής της συνεδρίας)")
            my_ids = st.session_state.get("my_last_orders", [])
            if my_ids:
                mine = load_orders().copy()
                mine = mine[mine["order_id"].isin(my_ids)]
                # κρύψε order_id, βάλε ελληνικές κεφαλίδες
                show = mine[["date","student","school","class","product","qty","unit_price","total"]].rename(columns={
                    "date":"Ημερομηνία","student":"Μαθητής/-τρια","school":"Σχολείο","class":"Τάξη",
                    "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)","total":"Σύνολο (€)"
                })
                st.dataframe(show, use_container_width=True)
                del_sel = st.multiselect("Επίλεξε γραμμές για διαγραφή", show.index.tolist())
                if st.button("🗑️ Διαγραφή επιλεγμένων"):
                    orders = load_orders().copy()
                    ids_to_del = mine.loc[del_sel, :].index
                    # map indices back to order_ids
                    order_ids_to_del = mine.loc[del_sel, :].assign(oid=mine.loc[del_sel, :].index).index
                    # simpler: find by merged keys
                    to_remove = mine.loc[del_sel, "order_id"].tolist()
                    orders = orders[~orders["order_id"].isin(to_remove)]
                    save_orders(orders)
                    st.session_state["my_last_orders"] = [x for x in my_ids if x not in to_remove]
                    st.success("Διαγράφηκαν οι επιλεγμένες γραμμές.")
                    st.rerun()
            else:
                st.info("Δεν υπάρχουν πρόσφατες καταχωρήσεις από αυτή τη συνεδρία.")

    # ----- TAB: Διόρθωση / Διαγραφή (admin ή και καταχώριση για δικές του)
    with tabs[1]:
        st.subheader("Διόρθωση / Διαγραφή")
        products = load_products()
        students = load_students()
        orders = load_orders().copy()

        # αν δεν είναι admin, φιλτράρω μόνο στις δικές του συνεδρίας για ασφάλεια
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
            # dropdown επιλογής
            df = df.sort_values("date", ascending=False).reset_index(drop=True)
            df["label"] = df.apply(lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['product']} (qty {int(r['qty']) if pd.notna(r['qty']) else ''})", axis=1)
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
                save_btn = st.form_submit_button("💾 Αποθήκευση αλλαγών")
            del_btn = st.button("🗑️ Διαγραφή γραμμής")

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
                # αφαίρεση από session "my_last_orders"
                st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x != oid]
                st.success("Η γραμμή διαγράφηκε.")
                st.rerun()

    st.divider()
    st.markdown("#### Πρόσφατες γραμμές (προεπισκόπηση)")
    prev = load_orders().sort_values("date", ascending=False).head(200)[["date","student","school","class","product","qty","unit_price","total"]].rename(columns={
        "date":"Ημερομηνία","student":"Μαθητής/-τρια","school":"Σχολείο","class":"Τάξη",
        "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)","total":"Σύνολο (€)"
    })
    st.dataframe(prev, use_container_width=True)

# --- Σύνοψη (όπως πριν, ήδη με ελληνικές κεφαλίδες)
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
            schools_filter = st.multiselect("Σχολεία", sorted(orders["school"].dropna().unique().tolist()))
        with c4:
            classes_filter = st.multiselect("Τάξεις", sorted(orders["class"].dropna().unique().tolist()))

        df = orders.copy()
        df = df[(df["date"]>=pd.to_datetime(d_from)) & (df["date"]<=pd.to_datetime(d_to))]
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
        ).sort_values("qty", ascending=False).rename(columns={"product":"Προϊόν","qty":"Ποσότητα","total":"Σύνολο (€)"})
        st.dataframe(by_product, use_container_width=True)

        to_excel_download({
            "Ανά μαθητή": by_student,
            "Ανά τάξη": by_class,
            "Ανά σχολείο": by_school,
            "Ανά προϊόν": by_product,
            "Αναλυτικά": df.sort_values(["school","class","student","date"]).rename(columns={
                "date":"Ημερομηνία","student":"Μαθητής/-τρια","school":"Σχολείο","class":"Τάξη",
                "product":"Προϊόν","qty":"Ποσότητα","unit_price":"Τιμή (€)","total":"Σύνολο (€)"
            })
        }, filename="αναφορές.xlsx")

        colp1, colp2, colp3, colp4 = st.columns(4)
        with colp1:
            if st.button("📄 PDF: Ανά μαθητή"):
                pdfbuf = pdf_table(by_student, title="Αναφορά ανά μαθητή/τρια", columns=[
                    ("Μαθητής/-τρια","Μαθητής/-τρια","L"),
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
                pdfbuf = pdf_products_report(by_product.rename(columns={"Προϊόν":"product","Ποσότητα":"qty","Σύνολο (€)":"total"}), title="Παραγγελία προς κατάστημα")
                st.download_button("⬇️ Λήψη", data=pdfbuf.getvalue(), file_name="προς_κατάστημα.pdf", mime="application/pdf")
