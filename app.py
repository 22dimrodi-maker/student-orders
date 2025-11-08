
import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import date, datetime

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
    return df

@st.cache_data
def load_students():
    if STUDENTS_PATH.exists():
        df = pd.read_csv(STUDENTS_PATH)
    else:
        df = pd.DataFrame(columns=["student"])
    df["student"] = df.get("student", "").astype(str)
    return df

@st.cache_data
def load_orders():
    if ORDERS_PATH.exists():
        df = pd.read_csv(ORDERS_PATH, parse_dates=["date"])
        # βεβαιωνόμαστε για τύπους
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["qty","unit_price","total"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    else:
        return pd.DataFrame(columns=["date","student","product","qty","unit_price","total"])

def save_products(df):
    df.to_csv(PRODUCTS_PATH, index=False, encoding="utf-8-sig")
    load_products.clear()

def save_students(df):
    df = df.dropna().copy()
    df["student"] = df["student"].astype(str).str.strip()
    df = df.loc[df["student"].str.len() > 0].drop_duplicates().sort_values("student")
    df.to_csv(STUDENTS_PATH, index=False, encoding="utf-8-sig")
    load_students.clear()

def save_orders(df):
    df.to_csv(ORDERS_PATH, index=False, encoding="utf-8-sig")
    load_orders.clear()

def to_excel_download(df_dict, filename="report.xlsx"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        for sheet, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return st.download_button("⬇️ Λήψη Excel", data=output.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.title("🍔 Παραγγελίες Μαθητών")
st.caption("Καταχώριση μαθητών, παραγγελιών, δελτίων και συνόψεων.")

page = st.sidebar.radio("Μενού", ["Κατάλογος", "Μαθητές", "Παραγγελίες", "Σύνοψη", "Δελτία"], index=4)

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
    st.dataframe(products, use_container_width=True)

# --- Μαθητές ---
elif page == "Μαθητές":
    st.subheader("Διαχείριση Μαθητών")
    students = load_students().copy()
    c1, c2 = st.columns([1,2])
    with c1:
        with st.form("add_student"):
            s = st.text_input("Ονοματεπώνυμο")
            subm = st.form_submit_button("➕ Προσθήκη")
        if subm and s.strip():
            if (students["student"].str.lower() == s.strip().lower()).any():
                st.warning("Υπάρχει ήδη.")
            else:
                students.loc[len(students)] = [s.strip()]
                save_students(students)
                st.success("Προστέθηκε.")
                st.rerun()
    with c2:
        st.markdown("**Ανέβασμα Excel με μαθητές**")
        st.caption("Ανεβάστε .xlsx με ονόματα στη **στήλη A** ή ένα φύλλο με στήλη **student**.")
        upl = st.file_uploader("Επιλογή αρχείου Excel", type=["xlsx"])
        if upl is not None:
            try:
                xl = pd.ExcelFile(upl)
                # Προσπαθούμε για στήλη "student", αλλιώς παίρνουμε την πρώτη στήλη του πρώτου φύλλου
                df_candidates = []
                for sh in xl.sheet_names:
                    df = pd.read_excel(xl, sheet_name=sh)
                    if "student" in df.columns:
                        df_candidates.append(df[["student"]])
                    else:
                        first_col = df.columns[0]
                        df_tmp = df[[first_col]].rename(columns={first_col: "student"})
                        df_candidates.append(df_tmp)
                merged = pd.concat(df_candidates, ignore_index=True)
                save_students(merged[["student"]])
                st.success("Οι μαθητές ενημερώθηκαν από το Excel.")
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα ανάγνωσης: {e}")
    st.markdown("#### Τρέχουσα λίστα")
    st.dataframe(load_students(), use_container_width=True)

# --- Παραγγελίες ---
elif page == "Παραγγελίες":
    st.subheader("Καταχώριση Παραγγελιών")
    products = load_products()
    students = load_students()
    orders = load_orders().copy()

    if students.empty or products.empty:
        st.info("Πρέπει να υπάρχουν μαθητές και προϊόντα για να προσθέσετε παραγγελίες.")
    else:
        with st.form("add_order", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2,2,1,1])
            with c1:
                d = st.date_input("Ημερομηνία", value=date.today())
            with c2:
                s = st.selectbox("Μαθητής", students["student"].tolist())
            with c3:
                p = st.selectbox("Προϊόν", products["product"].tolist())
            with c4:
                qty = st.number_input("Ποσότητα", min_value=1, value=1, step=1)
            submitted = st.form_submit_button("✅ Καταχώριση")
        if submitted:
            unit_price = float(products.loc[products["product"]==p, "price"].iloc[0])
            total = unit_price * qty
            new = pd.DataFrame([{
                "date": pd.to_datetime(d),
                "student": s,
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
            students_filter = st.multiselect("Μαθητές", sorted(orders["student"].dropna().unique().tolist()))
        with c2:
            products_filter = st.multiselect("Προϊόντα", sorted(orders["product"].dropna().unique().tolist()))
        with c3:
            date_min = st.date_input("Από", value=orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today())
            date_max = st.date_input("Έως", value=orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today())

        df = orders.copy()
        if date_min:
            df = df[df["date"] >= pd.to_datetime(date_min)]
        if date_max:
            df = df[df["date"] <= pd.to_datetime(date_max) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
        if students_filter:
            df = df[df["student"].isin(students_filter)]
        if products_filter:
            df = df[df["product"].isin(products_filter)]

        # Σύνοψη ανά μαθητή
        st.markdown("### Ανά μαθητή")
        by_student = df.groupby(["student"], as_index=False).agg(
            παραγγελίες=("total", "count"),
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values("σύνολο", ascending=False)
        st.dataframe(by_student, use_container_width=True)

        # Σύνοψη ανά προϊόν
        st.markdown("### Ανά προϊόν")
        by_product = df.groupby(["product"], as_index=False).agg(
            παραγγελίες=("total", "count"),
            ποσότητα=("qty", "sum"),
            σύνολο=("total", "sum")
        ).sort_values("σύνολο", ascending=False)
        st.dataframe(by_product, use_container_width=True)

        # Λήψη Excel
        to_excel_download({
            "Ανά μαθητή": by_student,
            "Ανά προϊόν": by_product,
            "Αναλυτικά": df.sort_values(["student","date"])
        }, filename="summary.xlsx")

# --- Δελτία ---
else:
    st.subheader("Δελτίο")

    orders = load_orders()
    products = load_products()
    students = load_students()

    if orders.empty:
        st.info("Δεν υπάρχουν ακόμη παραγγελίες.")
    else:
        # Φίλτρα περιόδου
        c1, c2, c3 = st.columns(3)
        with c1:
            date_min = st.date_input("Από", value=orders["date"].min().date() if pd.notna(orders["date"].min()) else date.today())
        with c2:
            date_max = st.date_input("Έως", value=orders["date"].max().date() if pd.notna(orders["date"].max()) else date.today())
        with c3:
            sel_student = st.selectbox("Μαθητής (ή Όλοι)", ["Όλοι"] + sorted(orders["student"].dropna().unique().tolist()))

        df = orders.copy()
        if date_min:
            df = df[df["date"] >= pd.to_datetime(date_min)]
        if date_max:
            df = df[df["date"] <= pd.to_datetime(date_max) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
        if sel_student != "Όλοι":
            df = df[df["student"] == sel_student]

        # Δελτίο ανά μαθητή: λίστα προϊόντων του και σύνολο
        if sel_student != "Όλοι":
            st.markdown(f"### Δελτίο: {sel_student}")
            per_student = df.groupby(["student","product","unit_price"], as_index=False).agg(
                qty=("qty","sum"),
                total=("total","sum")
            ).sort_values(["student","product"])
            st.dataframe(per_student[["product","unit_price","qty","total"]], use_container_width=True)
            total_sum = per_student["total"].sum()
            st.markdown(f"**Σύνολο:** {total_sum:.2f} €")
            # λήψη excel δελτίου
            to_excel_download({"Δελτίο": per_student, "Αναλυτικά": df.sort_values("date")}, filename=f"δελτιο_{sel_student}.xlsx")
        else:
            st.markdown("### Δελτίο: Όλοι οι μαθητές")
            # Αναλυτικό δελτίο: ανά μαθητή με σύνολο
            detail = df.groupby(["student","product","unit_price"], as_index=False).agg(
                qty=("qty","sum"),
                total=("total","sum")
            ).sort_values(["student","product"])
            st.dataframe(detail, use_container_width=True)
            # Σύνοψη ανά μαθητή
            by_student = df.groupby("student", as_index=False).agg(
                παραγγελίες=("total","count"),
                ποσότητα=("qty","sum"),
                σύνολο=("total","sum")
            ).sort_values("σύνολο", ascending=False)
            # Σύνοψη ανά προϊόν
            by_product = df.groupby("product", as_index=False).agg(
                παραγγελίες=("total","count"),
                ποσότητα=("qty","sum"),
                σύνολο=("total","sum")
            ).sort_values("σύνολο", ascending=False)

            st.markdown("#### Σύνοψη ανά μαθητή")
            st.dataframe(by_student, use_container_width=True)
            st.markdown("#### Σύνοψη ανά προϊόν")
            st.dataframe(by_product, use_container_width=True)

            to_excel_download({
                "Δελτίο αναλυτικό": detail,
                "Σύνοψη ανά μαθητή": by_student,
                "Σύνοψη ανά προϊόν": by_product,
                "Αναλυτικά": df.sort_values(["student","date"])
            }, filename="δελτιο_ολων.xlsx")
