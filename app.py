
import streamlit as st
import pandas as pd
import io, uuid, os
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

# ---------------- Seed demo ----------------
def seed_demo_data():
    prods = load_products()
    studs = load_students()
    changed = False
    if prods.empty:
        prods = pd.DataFrame([{"product":"Τοστ","price":2.0},{"product":"Χυμός","price":1.5}])
        prods.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
        (load_products.clear() if hasattr(load_products, "clear") else None)
        changed = True
    if studs.empty:
        studs = pd.DataFrame([{"student":"Δείγμα Μαθητή/τρια","school":"Δείγμα Σχολείο","class":"Α1"}])
        studs.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
        (load_students.clear() if hasattr(load_students, "clear") else None)
        changed = True
    return changed

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
            if seed_demo_data():
                st.success("Φορτώθηκαν δείγματα προϊόντων/μαθητών για δοκιμή.")
                st.rerun()
            st.info("Πρέπει να υπάρχουν μαθητές/τριες και προϊόντα. Συμπλήρωσέ τα από τα μενού ‘Κατάλογος’ και ‘Μαθητές’.")
        else:
            students = students.copy()
            students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
            c1, c2 = st.columns([1.2,3])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today(), key="order_date")
            with c2:
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
                save_click = st.button("✅ Καταχώριση παραγγελίας")
            with cbtn2:
                clear_click = st.button("🧹 Νέα παραγγελία")
            with cbtn3:
                add_row = st.button("➕ Προσθήκη γραμμής")

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
            df["label"] = df.apply(lambda r: f"{r['date'].date() if pd.notna(r['date']) else ''} • {r['student']} • {r['product']} (qty {int(r['qty']) if pd.notna(r['qty']) and int(r['qty'])>0 else ''})", axis=1)
            # ---- Μαζική διαγραφή παραγγελιών
            st.markdown("#### Μαζική διαγραφή παραγγελιών")
            bulk_sel = st.multiselect("Επίλεξε γραμμές", df["label"].tolist(), key="bulk_orders_select")
            confirm_bulk = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="bulk_orders_confirm")
            if st.button("🗑️ Διαγραφή επιλεγμένων παραγγελιών") and bulk_sel and confirm_bulk:
                oids = df.loc[df["label"].isin(bulk_sel), "order_id"].tolist()
                orders_all = load_orders().copy()
                orders_all = orders_all[~orders_all["order_id"].isin(oids)]
                save_orders(orders_all)
                if not is_admin:
                    st.session_state["my_last_orders"] = [x for x in st.session_state.get("my_last_orders", []) if x not in oids]
                st.success(f"Διαγράφηκαν {len(oids)} γραμμές.")
                st.rerun()
            mapping = dict(zip(df["label"], df["order_id"]))
            choice = st.selectbox("Διάλεξε γραμμή", df["label"].tolist())
            oid = mapping[choice]
            row = df[df["order_id"]==oid].iloc[0]

            with st.form("edit_line"):
                col1, col2, col3, col4, col5 = st.columns([1.2,1.8,2,1,1])
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
                    base_qty = int(row["qty"]) if pd.notna(row["qty"]) and int(row["qty"])>0 else 1
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

        # Excel export
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
            detail.to_excel(writer, sheet_name="Δελτίο", index=False)
        st.download_button("⬇️ Λήψη Excel", data=out.getvalue(), file_name="δελτιο.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if st.button("📄 Εξαγωγή PDF (ομαδοποιημένο ανά σχολείο/μαθητή)"):
            buffer = pdf_grouped_by_school_student(detail, title="Δελτίο Παραγγελιών")
            st.download_button("⬇️ Λήψη PDF", data=buffer.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")
