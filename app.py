
import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

st.set_page_config(page_title="Παραγγελίες Μαθητών", layout="wide")

DATA_DIR = Path(".")
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
ORDERS_PATH = DATA_DIR / "orders.csv"

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
        df = pd.DataFrame(columns=["date","student","school","class","product","qty","unit_price","total"])
    for c in ["date","student","school","class","product","qty","unit_price","total"]:
        if c not in df.columns:
            df[c] = pd.NA
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["qty","unit_price","total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["student","school","class","product"]:
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
    cols = ["date","student","school","class","product","qty","unit_price","total"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[cols]
    df.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    load_orders.clear()

def to_excel_download(df_dict, filename="report.xlsx"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        for sheet, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return st.download_button("⬇️ Λήψη Excel", data=output.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def pdf_grouped_by_school_student(df, title="Δελτίο"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 2*cm
    right = width - 2*cm
    y = height - 2*cm

    def draw_header(page_title):
        nonlocal y
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left, y, page_title)
        c.setFont("Helvetica", 9)
        c.drawRightString(right, y, f"Ημερομηνία εξαγωγής: {pd.Timestamp.today().date()}")
        y -= 0.8*cm

    def new_page(page_title):
        nonlocal y
        c.showPage()
        y = height - 2*cm
        draw_header(page_title)

    draw_header(title)

    grand_total = 0.0
    for school, g1 in df.groupby("school"):
        if y < 3*cm: new_page(title)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y, f"Σχολείο: {school or '—'}")
        y -= 0.6*cm

        school_total = 0.0
        for student, g2 in g1.groupby("student"):
            if y < 3*cm: new_page(title)
            c.setFont("Helvetica-Bold", 11)
            cls = (g2["class"].iloc[0] or "").strip()
            suffix = f" — Τάξη: {cls}" if cls else ""
            c.drawString(left, y, f"Μαθητής/-τρια: {student}{suffix}")
            y -= 0.5*cm

            c.setFont("Helvetica-Bold", 9)
            c.drawString(left, y, "Προϊόν")
            c.drawRightString(right-6.5*cm, y, "Τιμή (€)")
            c.drawRightString(right-3.5*cm, y, "Ποσότητα")
            c.drawRightString(right-0.5*cm, y, "Σύνολο (€)")
            y -= 0.4*cm
            c.setFont("Helvetica", 9)

            subtotal = 0.0
            for _, row in g2.sort_values(["product"]).iterrows():
                if y < 2*cm: new_page(title)
                c.drawString(left, y, str(row["product"]))
                c.drawRightString(right-6.5*cm, y, f"{row['unit_price']:.2f}")
                c.drawRightString(right-3.5*cm, y, f"{int(row['qty']) if pd.notna(row['qty']) else ''}")
                c.drawRightString(right-0.5*cm, y, f"{row['total']:.2f}")
                y -= 0.35*cm
                subtotal += float(row["total"] or 0)

            if y < 2*cm: new_page(title)
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(right-0.5*cm, y, f"Σύνολο {student}: {subtotal:.2f} €")
            y -= 0.5*cm
            c.setFont("Helvetica", 9)
            school_total += subtotal

        if y < 2*cm: new_page(title)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(right-0.5*cm, y, f"Σύνολο Σχολείου: {school_total:.2f} €")
        y -= 0.7*cm
        grand_total += school_total

    if y < 2*cm: new_page(title)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right-0.5*cm, y, f"Γενικό Σύνολο: {grand_total:.2f} €")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

st.title("🍔 Παραγγελίες Μαθητών")
st.caption("Μαθητές από πολλά σχολεία, παραγγελίες, PDF δελτία και συνόψεις.")

page = st.sidebar.radio("Μενού", ["Κατάλογος", "Μαθητές", "Παραγγελίες", "Σύνοψη", "Δελτία"], index=1)

# --- Κατάλογος ---
if page == "Κατάλογος":
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
    st.caption("Δεκτό .xlsx με επικεφαλίδες **Προϊόν** & **Τιμή**, ή αγγλικά `product` & `price`. Χωρίς επικεφαλίδες: 1η στήλη προϊόν, 2η τιμή.")
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

    st.markdown("#### Διαγραφή προϊόντος (μεμονωμένη)")
    if not products.empty:
        to_delete = st.selectbox("Επίλεξε προϊόν για διαγραφή", products["product"].tolist(), key="del_prod_single")
        confirm = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="confirm_prod_single")
        if st.button("🗑️ Διαγραφή προϊόντος") and confirm:
            products = products[products["product"] != to_delete].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκε: {to_delete}")
            st.rerun()
    else:
        st.info("Δεν υπάρχουν προϊόντα.")

    st.markdown("#### Μαζική διαγραφή προϊόντων")
    if not products.empty:
        multi_del = st.multiselect("Επίλεξε πολλά προϊόντα για διαγραφή", products["product"].tolist(), key="del_prod_multi")
        confirm_multi = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="confirm_prod_multi")
        if st.button("🗑️ Διαγραφή επιλεγμένων") and multi_del and confirm_multi:
            products = products[~products["product"].isin(multi_del)].reset_index(drop=True)
            save_products(products)
            st.success(f"Διαγράφηκαν: {', '.join(multi_del)}")
            st.rerun()

    st.markdown("#### Λίστα προϊόντων")
    st.dataframe(products, use_container_width=True)

# --- Μαθητές ---
elif page == "Μαθητές":
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
    st.caption("Δεκτό .xlsx με επικεφαλίδες **Ονοματεπώνυμο**, **Σχολείο**, **Τάξη**. Γίνονται και αντιστοιχίσεις σε `student`/`school`/`class`. Χωρίς headers: 1η στήλη Ονοματεπώνυμο, 2η Σχολείο, 3η Τάξη (προαιρετική).")
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

    st.markdown("#### Διαγραφή μαθητή/-ριας (μεμονωμένα)")
    if not students.empty:
        students = load_students().copy()
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
        sel = st.selectbox("Επίλεξε για διαγραφή", students["label"].tolist(), key="del_student_single")
        confirm = st.checkbox("✅ Επιβεβαίωση διαγραφής", key="confirm_st_single")
        if st.button("🗑️ Διαγραφή μαθητή/-ριας") and confirm:
            idx = students.index[students["label"]==sel][0]
            name_del = students.loc[idx, "label"]
            students = students.drop(index=idx).drop(columns=["label"]).reset_index(drop=True)
            save_students(students)
            st.success(f"Διαγράφηκε: {name_del}")
            st.rerun()
    else:
        st.info("Δεν υπάρχουν μαθητές.")

    st.markdown("#### Μαζική διαγραφή ανά σχολείο/τάξη")
    all_students = load_students()
    schools = sorted([s for s in all_students["school"].dropna().unique().tolist() if str(s).strip()])
    col1, col2 = st.columns(2)
    with col1:
        sch_sel = st.multiselect("Σχολεία", schools, key="del_schools_multi")
    with col2:
        classes = sorted([c for c in all_students["class"].dropna().unique().tolist() if str(c).strip()])
        cls_sel = st.multiselect("Τάξεις (προαιρετικά)", classes, key="del_classes_multi")
    confirm_bulk = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="confirm_st_bulk")
    if st.button("🗑️ Διαγραφή όλων/ων από επιλογές") and sch_sel and confirm_bulk:
        remain = all_students[~all_students["school"].isin(sch_sel)].copy()
        if cls_sel:
            remain = all_students[~(all_students["school"].isin(sch_sel) & all_students["class"].isin(cls_sel))]
        save_students(remain.reset_index(drop=True))
        st.success("Ολοκληρώθηκε.")
        st.rerun()

    st.markdown("#### Τρέχουσα λίστα")
    st.dataframe(load_students(), use_container_width=True)

# --- Παραγγελίες ---
elif page == "Παραγγελίες":
    st.subheader("Καταχώριση Παραγγελιών")
    products = load_products()
    students = load_students()
    orders = load_orders().copy()

    if students.empty or products.empty:
        st.info("Πρέπει να υπάρχουν μαθητές/τριες και προϊόντα.")
    else:
        students = students.copy()
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']} — {r['class']}" if (str(r["school"]).strip() or str(r["class"]).strip()) else r["student"], axis=1)
        with st.form("add_order", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2,2,1,1])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today())
            with c2:
                label = st.selectbox("Μαθητής/-τρια", students["label"].tolist())
            with c3:
                p = st.selectbox("Προϊόν", products["product"].tolist())
            with c4:
                qty = st.number_input("Ποσότητα", min_value=1, value=1, step=1)
            submitted = st.form_submit_button("✅ Καταχώριση")
        if submitted:
            row = students.loc[students["label"]==label].iloc[0]
            s = row["student"]
            sch = row["school"]
            cl = row["class"]
            unit_price = float(products.loc[products["product"]==p, "price"].iloc[0])
            total = unit_price * qty
            new = pd.DataFrame([{
                "date": pd.to_datetime(d),
                "student": s,
                "school": sch,
                "class": cl,
                "product": p,
                "qty": qty,
                "unit_price": unit_price,
                "total": total
            }])
            orders = pd.concat([orders, new], ignore_index=True)
            save_orders(orders)
            st.success("Η παραγγελία καταχωρήθηκε.")
            st.rerun()

    st.markdown("#### Πρόσφατες παραγγελίες")
    st.dataframe(load_orders().sort_values("date", ascending=False), use_container_width=True)

# --- Σύνοψη ---
elif page == "Σύνοψη":
    st.subheader("Σύνοψη")
    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
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
        if students_filter:
            df = df[df["student"].isin(students_filter)]
        if products_filter:
            df = df[df["product"].isin(products_filter)]
        if schools_filter:
            df = df[df["school"].isin(schools_filter)]
        if classes_filter:
            df = df[df["class"].isin(classes_filter)]

        st.markdown("### Ανά μαθητή/-τρια")
        by_student = df.groupby(["student","school","class"], as_index=False).agg(
            παραγγελίες=("total", "count"),
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values(["school","class","student"])
        st.dataframe(by_student, use_container_width=True)

        st.markdown("### Ανά προϊόν")
        by_product = df.groupby(["product"], as_index=False).agg(
            παραγγελίες=("total", "count"),
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values("σύνολο", ascending=False)
        st.dataframe(by_product, use_container_width=True)

        to_excel_download({
            "Ανά μαθητή": by_student,
            "Ανά προϊόν": by_product,
            "Αναλυτικά": df.sort_values(["school","class","student","date"])
        }, filename="summary.xlsx")

# --- Δελτία ---
else:
    st.subheader("Δελτίο & Εκτύπωση PDF")
    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
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
        if sel_school != "Όλα":
            df = df[df["school"] == sel_school]
        if sel_class != "Όλες":
            df = df[df["class"] == sel_class]
        if sel_student != "Όλοι/-ες":
            df = df[df["student"] == sel_student]

        detail = df.groupby(["student","school","class","product","unit_price"], as_index=False).agg(
            qty=("qty","sum"),
            total=("total","sum")
        ).sort_values(["school","class","student","product"])
        st.dataframe(detail, use_container_width=True)

        by_student = df.groupby(["student","school","class"], as_index=False).agg(
            παραγγελίες=("total","count"),
            ποσότητα=("qty","sum"),
            σύνολο=("total","sum")
        ).sort_values(["school","class","student"])
        by_product = df.groupby(["product"], as_index=False).agg(
            παραγγελίες=("total","count"),
            ποσότητα=("qty","sum"),
            σύνολο=("total","sum")
        ).sort_values("σύνολο", ascending=False)

        to_excel_download({
            "Δελτίο αναλυτικό": detail,
            "Σύνοψη ανά μαθητή": by_student,
            "Σύνοψη ανά προϊόν": by_product
        }, filename="δελτιο.xlsx")

        if st.button("📄 Εξαγωγή PDF (ομαδοποιημένο ανά σχολείο/μαθητή)"):
            buffer = pdf_grouped_by_school_student(detail, title="Δελτίο Παραγγελιών")
            st.download_button("⬇️ Λήψη PDF", data=buffer.getvalue(), file_name="δελτιο.pdf", mime="application/pdf")
