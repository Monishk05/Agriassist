# dashboard.py
import streamlit as st
import sqlite3
import json
import base64
import pandas as pd
import os
from datetime import datetime
from fpdf import FPDF

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="AgriAssist Admin",
    page_icon="leaf",
    layout="wide"
)

# ====================== TITLE ======================
st.title("AgriAssist – Admin Dashboard")
st.caption("View, filter, escalate, and export farmer cases")

# ====================== DATABASE ======================
DB_PATH = "agriassist.db"

if not os.path.exists(DB_PATH):
    st.error(f"Database not found: `{DB_PATH}`")
    st.info("Run your bot first: `python main.py`")
    st.stop()

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM cases ORDER BY id DESC", conn)
conn.close()

if df.empty:
    st.info("No cases yet. Send a crop photo via WhatsApp!")
    st.stop()

# ====================== SIDEBAR FILTERS ======================
st.sidebar.header("Filters")

search_phone = st.sidebar.text_input("Search Phone", "")
min_conf = st.sidebar.slider("Min Confidence (%)", 0, 100, 0)
show_escalated = st.sidebar.checkbox("Escalated Cases Only", False)

# Apply filters
filtered = df.copy()

if search_phone:
    filtered = filtered[filtered["phone"].str.contains(search_phone, case=False, na=False)]

if min_conf > 0:
    filtered = filtered[filtered["diagnosis_json"].apply(
        lambda x: json.loads(x).get("confidence", 0) >= min_conf
    )]

if show_escalated:
    filtered = filtered[filtered["escalated"] == 1]

st.sidebar.success(f"**{len(filtered)} cases** shown")

# ====================== PARSE JSON ======================
def parse_diag(json_str):
    try:
        d = json.loads(json_str)
        return {
            "Diagnosis": d.get("diagnosis", "—"),
            "English": d.get("english_name", "—"),
            "Confidence": f"{d.get('confidence', 0)}%",
            "Cost": f"₹{d.get('estimated_cost_inr', 0)}",
            "Escalate": "YES" if d.get("escalate") else "NO"
        }
    except:
        return {"Diagnosis": "Error", "English": "", "Confidence": "", "Cost": "", "Escalate": "—"}

parsed = filtered.apply(lambda row: parse_diag(row["diagnosis_json"]), axis=1, result_type="expand")
display_df = pd.concat([filtered[["id", "phone", "timestamp"]], parsed], axis=1)
display_df = display_df.loc[:, ~display_df.columns.duplicated()]
display_df["timestamp"] = pd.to_datetime(display_df["timestamp"], errors="coerce").dt.strftime("%b %d, %I:%M %p")
# ====================== MAIN TABLE ======================
st.subheader("All Cases")
st.dataframe(display_df, use_container_width=True, hide_index=True)

# ====================== CASE DETAILS ======================
st.subheader("Case Details")
selected_id = st.selectbox("Select Case ID", options=filtered["id"].tolist(), key="case_select")

if selected_id:
    case = filtered[filtered["id"] == selected_id].iloc[0]
    diag = json.loads(case["diagnosis_json"])

    col1, col2 = st.columns([1, 2])

    with col1:
        st.image(
            base64.b64decode(case["image_b64"]),
            caption=f"From: {case['phone']}",
            use_column_width=True
        )

    with col2:
        st.write(f"**Phone:** `{case['phone']}`")
        st.write(f"**Time:** {case['timestamp']}")
        st.write(f"**Diagnosis:** {diag.get('diagnosis')}")
        st.write(f"**English Name:** {diag.get('english_name')}")
        st.write(f"**Confidence:** {diag.get('confidence', 0)}%")
        st.write(f"**Estimated Cost:** ₹{diag.get('estimated_cost_inr', 0)}")
        st.write(f"**Escalated:** {'YES' if diag.get('escalate') else 'NO'}")

        st.markdown("### Symptoms")
        for s in diag.get("symptoms_match", []):
            st.write(f"• {s}")

        st.markdown("### Treatment Steps")
        for step in diag.get("treatment_steps", []):
            st.write(step)

        st.markdown("### Precautions")
        st.write(diag.get("precautions", "—"))

    # ====================== ESCALATE BUTTON ======================
    if not diag.get("escalate"):
        if st.button("Escalate to Expert", type="primary", use_container_width=True):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE cases SET escalated = 1 WHERE id = ?", (selected_id,))
            conn.commit()
            conn.close()
            st.success("Case escalated!")
            st.balloons()
            st.experimental_rerun()

    # ====================== DOWNLOAD PDF ======================
    if st.button("Download PDF Report", use_container_width=True):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(200, 10, txt="AgriAssist Case Report", ln=1, align="C")
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Case ID: {selected_id}", ln=1)
        pdf.cell(200, 10, txt=f"Phone: {case['phone']}", ln=1)
        pdf.cell(200, 10, txt=f"Time: {case['timestamp']}", ln=1)
        pdf.ln(10)

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="Diagnosis:", ln=1)
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, diag.get("diagnosis", ""))

        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="Treatment:", ln=1)
        pdf.set_font("Arial", size=12)
        for step in diag.get("treatment_steps", []):
            pdf.multi_cell(0, 10, f"• {step}")

        pdf_file = f"agriassist_report_{selected_id}.pdf"
        pdf.output(pdf_file)

        with open(pdf_file, "rb") as f:
            st.download_button(
                label="Download PDF",
                data=f,
                file_name=pdf_file,
                mime="application/pdf",
                use_container_width=True
            )