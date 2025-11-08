
import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import date

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
    df["price"] = pd.to_numeric(df.get("price", 0), errors="coerce").fillna(0.0)
    df["product"] = df.get("product","").astype(str).str.strip()
    return df

@st.cache_data
def load_students():
    if STUDENTS_PATH.exists():
        df = pd.read_csv(STUDENTS_PATH)
    else:
        df = pd.DataFrame(columns=["student","school"])
    if "school" not in df.columns:
        df["school"] = ""
    df["student"] = df.get("student", "").astype(str).str.strip()
    df["school"] = df.get("school", "").astype(str).str.strip()
    return df

@st.cache_data
def load_orders():
    if ORDERS_PATH.exists():
        df = pd.read_csv(ORDERS_PATH, parse_dates=["date"])
    else:
        df = pd.DataFrame(columns=["date","student","school","product","qty","unit_price","total"])
    # Ensure columns
    for c in ["date","student","school","product","qty","unit_price","total"]:
        if c not in df.columns:
            df[c] = pd.NA
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["qty","unit_price","total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["student"] = df["student"].astype(str).str.strip()
    df["school"] = df["school"].astype(str).str.strip()
    df["product"] = df["product"].astype(str).str.strip()
    return df

def save_products(df):
    df = df[["product","price"]].copy()
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df.dropna().drop_duplicates(subset=["product"]).sort_values("product")
    df.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    load_products.clear()

def save_students(df):
    # Normalize to student, school
    if "school" not in df.columns:
        df["school"] = ""
    df = df[["student","school"]].dropna().copy()
    df["student"] = df["student"].astype(str).str.strip()
    df["school"] = df["school"].astype(str).str.strip()
    df = df.loc[df["student"].str.len() > 0]
    df = df.drop_duplicates(subset=["student","school"]).sort_values(["student","school"])
    df.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    load_students.clear()

def save_orders(df):
    # Ensure column order
    cols = ["date","student","school","product","qty","unit_price","total"]
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

st.title("🍔 Παραγγελίες Μαθητών")
st.caption("Μαθητές από πολλά σχολεία, παραγγελίες, διαγραφές και σύνοψη.")

page = st.sidebar.radio("Μενού", ["Κατάλογος", "Μαθητές", "Παραγγελίες", "Σύνοψη", "Δελτία"], index=1)

# --- Κατάλογος (με διαγραφή & μαζική διαγραφή) ---
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

# --- Μαθητές (upload Excel με Ονοματεπώνυμο & Σχολείο + διαγραφή) ---
elif page == "Μαθητές":
    st.subheader("Διαχείριση Μαθητών & Σχολείων")
    students = load_students().copy()

    # Προσθήκη με φόρμα
    with st.form("add_student"):
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            s = st.text_input("Ονοματεπώνυμο")
        with c2:
            sch = st.text_input("Σχολείο", placeholder="π.χ. 1ο Γυμνάσιο")
        submitted = st.form_submit_button("➕ Προσθήκη")
    if submitted and s.strip():
        exists = ((students["student"].str.lower()==s.strip().lower()) & (students["school"].str.lower()==sch.strip().lower())).any()
        if exists:
            st.warning("Υπάρχει ήδη.")
        else:
            students.loc[len(students)] = [s.strip(), sch.strip()]
            save_students(students)
            st.success("Προστέθηκε.")
            st.rerun()

    # Upload Excel με Ονοματεπώνυμο & Σχολείο
    st.markdown("**Ανέβασμα Excel: Ονοματεπώνυμο & Σχολείο**")
    st.caption("Δεκτό .xlsx με επικεφαλίδες **Ονοματεπώνυμο** και **Σχολείο** (ή χωρίς επικεφαλίδες: 1η στήλη Ονοματεπώνυμο, 2η Σχολείο). Γίνονται και αντιστοιχίσεις σε `student`/`school`.")
    upl = st.file_uploader("Επιλογή αρχείου Excel", type=["xlsx"])
    if upl is not None:
        try:
            xl = pd.ExcelFile(upl)
            frames = []
            for sh in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sh)
                # ομογενοποίηση ονομάτων στηλών
                norm = {str(c).strip(): str(c).strip().lower() for c in df.columns}
                df = df.rename(columns=norm)
                # πρώτα προσπαθούμε ελληνικά headers
                if "ονοματεπώνυμο" in df.columns and "σχολείο" in df.columns:
                    tmp = df.rename(columns={"ονοματεπώνυμο":"student","σχολείο":"school"})[["student","school"]]
                # μετά αγγλικά headers
                elif "student" in df.columns:
                    if "school" not in df.columns:
                        df["school"] = ""
                    tmp = df[["student","school"]]
                else:
                    # χωρίς headers -> παίρνουμε τις 2 πρώτες στήλες
                    if df.shape[1] >= 2:
                        tmp = df.iloc[:, :2].copy()
                        tmp.columns = ["student","school"]
                    else:
                        tmp = df.iloc[:, :1].copy()
                        tmp.columns = ["student"]
                        tmp["school"] = ""
                frames.append(tmp[["student","school"]])
            merged = pd.concat(frames, ignore_index=True)
            save_students(pd.concat([students, merged], ignore_index=True))
            st.success("Οι μαθητές ενημερώθηκαν από το Excel.")
            st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα ανάγνωσης: {e}")

    # Διαγραφή μεμονωμένου/ης
    st.markdown("#### Διαγραφή μαθητή/-ριας (μεμονωμένα)")
    if not students.empty:
        students = load_students().copy()
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']}" if str(r["school"]).strip() else r["student"], axis=1)
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

    # Μαζική διαγραφή ανά σχολείο
    st.markdown("#### Μαζική διαγραφή ανά σχολείο")
    all_students = load_students()
    schools = sorted([s for s in all_students["school"].dropna().unique().tolist() if str(s).strip()])
    if schools:
        sch_sel = st.multiselect("Επίλεξε σχολεία", schools, key="del_schools_multi")
        confirm_bulk = st.checkbox("✅ Επιβεβαίωση μαζικής διαγραφής", key="confirm_st_bulk")
        if st.button("🗑️ Διαγραφή όλων/ων από επιλεγμένα σχολεία") and sch_sel and confirm_bulk:
            remain = all_students[~all_students["school"].isin(sch_sel)].reset_index(drop=True)
            save_students(remain)
            st.success(f"Διαγράφηκαν όλα τα άτομα από: {', '.join(sch_sel)}")
            st.rerun()
    else:
        st.caption("Δεν υπάρχουν καταγεγραμμένα σχολεία για μαζική διαγραφή.")

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
        students["label"] = students.apply(lambda r: f"{r['student']} — {r['school']}" if str(r["school"]).strip() else r["student"], axis=1)
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
            unit_price = float(products.loc[products["product"]==p, "price"].iloc[0])
            total = unit_price * qty
            new = pd.DataFrame([{
                "date": pd.to_datetime(d),
                "student": s,
                "school": sch,
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
        # φίλτρα
        c1, c2, c3 = st.columns(3)
        with c1:
            students_filter = st.multiselect("Μαθητές/-τριες", sorted(orders["student"].dropna().unique().tolist()))
        with c2:
            products_filter = st.multiselect("Προϊόντα", sorted(orders["product"].dropna().unique().tolist()))
        with c3:
            schools_filter = st.multiselect("Σχολεία", sorted(orders["school"].dropna().unique().tolist()))

        df = orders.copy()
        if students_filter:
            df = df[df["student"].isin(students_filter)]
        if products_filter:
            df = df[df["product"].isin(products_filter)]
        if schools_filter:
            df = df[df["school"].isin(schools_filter)]

        st.markdown("### Ανά μαθητή/-τρια")
        by_student = df.groupby(["student","school"], as_index=False).agg(
            παραγγελίες=("total", "count"),
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values(["school","student"])
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
            "Αναλυτικά": df.sort_values(["school","student","date"])
        }, filename="summary.xlsx")

# --- Δελτία ---
else:
    st.subheader("Δελτίο")

    orders = load_orders()

    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
        # Φίλτρα
        c1, c2 = st.columns(2)
        with c1:
            sel_school = st.selectbox("Σχολείο (ή Όλα)", ["Όλα"] + sorted(orders["school"].dropna().unique().tolist()))
        with c2:
            df_students = orders if sel_school=="Όλα" else orders[orders["school"]==sel_school]
            names = sorted(df_students["student"].dropna().unique().tolist())
            sel_student = st.selectbox("Μαθητής/-τρια (ή Όλοι)", ["Όλοι"] + names)

        df = orders.copy()
        if sel_school != "Όλα":
            df = df[df["school"] == sel_school]
        if sel_student != "Όλοι":
            df = df[df["student"] == sel_student]

        if sel_student != "Όλοι":
            st.markdown(f"### Δελτίο: {sel_student} ({sel_school if sel_school!='Όλα' else df[df['student']==sel_student]['school'].iloc[0]})")
            per_student = df.groupby(["student","school","product","unit_price"], as_index=False).agg(
                qty=("qty","sum"),
                total=("total","sum")
            ).sort_values(["product"])
            st.dataframe(per_student[["product","unit_price","qty","total"]], use_container_width=True)
            total_sum = per_student["total"].sum()
            st.markdown(f"**Σύνολο:** {total_sum:.2f} €")
            to_excel_download({"Δελτίο": per_student}, filename=f"δελτιο_{sel_student}.xlsx")
        else:
            st.markdown("### Δελτίο: Όλοι/ες")
            detail = df.groupby(["student","school","product","unit_price"], as_index=False).agg(
                qty=("qty","sum"),
                total=("total","sum")
            ).sort_values(["school","student","product"])
            st.dataframe(detail, use_container_width=True)

            by_student = df.groupby(["student","school"], as_index=False).agg(
                παραγγελίες=("total","count"),
                ποσότητα=("qty","sum"),
                σύνολο=("total","sum")
            ).sort_values(["school","student"])

            by_product = df.groupby("product", as_index=False).agg(
                παραγγελίες=("total","count"),
                ποσότητα=("qty","sum"),
                σύνολο=("total","sum")
            ).sort_values("σύνολο", ascending=False)

            st.markdown("#### Σύνοψη ανά μαθητή/-τρια")
            st.dataframe(by_student, use_container_width=True)
            st.markdown("#### Σύνοψη ανά προϊόν")
            st.dataframe(by_product, use_container_width=True)

            to_excel_download({
                "Δελτίο αναλυτικό": detail,
                "Σύνοψη ανά μαθητή": by_student,
                "Σύνοψη ανά προϊόν": by_product
            }, filename="δελτιο_ολων.xlsx")
