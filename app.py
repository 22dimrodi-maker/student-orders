import streamlit as st
import pandas as pd
import uuid
import os
import zipfile
from pathlib import Path
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import qrcode

# =============================
# CONFIG
# =============================

APP_PASSWORD = "1966"
ADMIN_PIN = "1966"

DATA_DIR = Path(".")
ORDERS_PATH = DATA_DIR / "orders.csv"
PRODUCTS_PATH = DATA_DIR / "products.csv"
STUDENTS_PATH = DATA_DIR / "students.csv"
LOGO_PATH = DATA_DIR / "logo.png"
BACKUP_DIR = DATA_DIR / "backups"

BACKUP_DIR.mkdir(exist_ok=True)

# =============================
# AUTH
# =============================

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    pw = st.text_input("Κωδικός πρόσβασης", type="password")
    if pw == APP_PASSWORD:
        st.session_state.auth = True
        st.rerun()
    st.stop()

# =============================
# HELPERS
# =============================

def dedupe_columns(df):
    return df.loc[:, ~df.columns.duplicated()].copy()

def clean_products_df(df):
    df = dedupe_columns(df)
    df.columns = [str(c).strip().lower() for c in df.columns]

    rename = {
        "προϊόν": "product",
        "προιον": "product",
        "τιμή": "price",
        "τιμη": "price",
        "τιμή (€)": "price",
        "τιμη (€)": "price",
    }
    df = df.rename(columns={c: rename.get(c, c) for c in df.columns})
    df = dedupe_columns(df)

    if "product" not in df.columns:
        df = df.rename(columns={df.columns[0]: "product"})
    if "price" not in df.columns:
        df["price"] = 0.0

    df = df[["product", "price"]].copy()
    df["product"] = df["product"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df[df["product"] != ""]
    df = df.drop_duplicates("product")
    return df.sort_values("product").reset_index(drop=True)

def clean_students_df(df):
    df = dedupe_columns(df)
    df.columns = [str(c).strip().lower() for c in df.columns]

    rename = {
        "ονοματεπώνυμο": "student",
        "μαθητής": "student",
        "σχολείο": "school",
        "τάξη": "class"
    }
    df = df.rename(columns={c: rename.get(c, c) for c in df.columns})
    df = dedupe_columns(df)

    if "student" not in df.columns:
        df = df.rename(columns={df.columns[0]: "student"})
    if "school" not in df.columns:
        df["school"] = ""
    if "class" not in df.columns:
        df["class"] = ""

    df = df[["student", "school", "class"]]
    df = df[df["student"] != ""]
    return df.sort_values(["school", "class", "student"]).reset_index(drop=True)

def load_products():
    if PRODUCTS_PATH.exists():
        df = pd.read_csv(PRODUCTS_PATH)
        return clean_products_df(df)
    return pd.DataFrame(columns=["product", "price"])

def save_products(df):
    df = clean_products_df(df)
    df.to_csv(PRODUCTS_PATH, index=False)

def load_students():
    if STUDENTS_PATH.exists():
        df = pd.read_csv(STUDENTS_PATH)
        return clean_students_df(df)
    return pd.DataFrame(columns=["student", "school", "class"])

def save_students(df):
    df = clean_students_df(df)
    df.to_csv(STUDENTS_PATH, index=False)

def load_orders():
    if ORDERS_PATH.exists():
        return pd.read_csv(ORDERS_PATH)
    return pd.DataFrame(columns=["order_id","date","student","school","product","qty","price","total"])

def save_orders(df):
    df.to_csv(ORDERS_PATH, index=False)
    snapshot = BACKUP_DIR / f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(snapshot, index=False)

# =============================
# MENU
# =============================

menu = st.sidebar.radio("Μενού", [
    "Καταχώριση",
    "Διόρθωση / Διαγραφή",
    "Δελτίο",
    "Κατάλογος",
    "Μαθητές",
    "Backup"
])

# =============================
# ΚΑΤΑΧΩΡΙΣΗ
# =============================

if menu == "Καταχώριση":

    products = load_products()
    students = load_students()

    if products.empty or students.empty:
        st.warning("Φόρτωσε πρώτα προϊόντα και μαθητές.")
        st.stop()

    student = st.selectbox("Μαθητής/τρια", students["student"])
    school = students.loc[students["student"] == student, "school"].values[0]

    st.markdown("---")

    order_rows = st.session_state.get("order_rows", [])
    if st.button("➕ Προσθήκη γραμμής"):
        order_rows.append({"product":"", "qty":1})
        st.session_state.order_rows = order_rows

    total_order = 0

    for i,row in enumerate(order_rows):
        cols = st.columns([3,1,1,1])
        product = cols[0].selectbox("Προϊόν", products["product"], key=f"p{i}")
        qty = cols[1].number_input("Ποσότητα", 1, 100, 1, key=f"q{i}")
        price = products.loc[products["product"]==product,"price"].values[0]
        partial = price * qty
        cols[2].write(f"{price:.2f} €")
        cols[3].write(f"{partial:.2f} €")
        total_order += partial
        order_rows[i] = {"product":product,"qty":qty}

    st.markdown(f"### Σύνολο τρέχουσας παραγγελίας: {total_order:.2f} €")

    if st.button("💾 Αποθήκευση"):
        orders = load_orders()
        order_id = str(uuid.uuid4())
        for row in order_rows:
            price = products.loc[products["product"]==row["product"],"price"].values[0]
            orders = pd.concat([orders,pd.DataFrame([{
                "order_id":order_id,
                "date":datetime.now().strftime("%Y-%m-%d"),
                "student":student,
                "school":school,
                "product":row["product"],
                "qty":row["qty"],
                "price":price,
                "total":price*row["qty"]
            }])])
        save_orders(orders)
        st.success("Αποθηκεύτηκε.")
        st.session_state.order_rows = []
        st.rerun()

# =============================
# ΔΕΛΤΙΟ PDF
# =============================

if menu == "Δελτίο":

    orders = load_orders()
    if orders.empty:
        st.info("Δεν υπάρχουν παραγγελίες.")
        st.stop()

    student = st.selectbox("Επιλογή μαθητή/τριας", orders["student"].unique())
    df = orders[orders["student"]==student]

    total = df["total"].sum()

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2*cm

    if LOGO_PATH.exists():
        c.drawImage(str(LOGO_PATH), 1*cm, height-3*cm, width=2*cm, preserveAspectRatio=True)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(1*cm, y, "ΔΕΛΤΙΟ ΠΑΡΑΓΓΕΛΙΑΣ")
    y -= 1*cm

    c.setFont("Helvetica", 11)
    c.drawString(1*cm, y, "Μαθητής/τρια:")
    y -= 0.5*cm
    c.drawString(1*cm, y, student)
    y -= 1*cm

    for _,row in df.iterrows():
        c.drawString(1*cm, y, f"{row['product']}  x{row['qty']}  =  {row['total']:.2f} €")
        y -= 0.7*cm

    y -= 0.5*cm
    c.line(1*cm,y,width-1*cm,y)
    y -= 0.7*cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*cm, y, f"Τελικό σύνολο: {total:.2f} €")

    c.save()
    buffer.seek(0)

    st.download_button("📄 Λήψη PDF", buffer, file_name="deltio.pdf")

# =============================
# BACKUP
# =============================

if menu == "Backup":
    if st.text_input("Admin PIN", type="password") != ADMIN_PIN:
        st.stop()

    if st.button("⚡ Γρήγορο Backup τώρα"):
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer,"w") as z:
            for f in [ORDERS_PATH, PRODUCTS_PATH, STUDENTS_PATH]:
                if f.exists():
                    z.write(f)
        zip_buffer.seek(0)
        st.download_button("Λήψη Backup", zip_buffer, "backup.zip")
