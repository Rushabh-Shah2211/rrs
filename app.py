import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import date
import os
import easyocr
import numpy as np
from PIL import Image
import random

# --- FILE PATHS & CONFIG ---
DB_FILE = "tasks_db.csv"
ICON_ICO = "icon.ico"
ICON_PNG = "icon.png"
THEME_COLOR = "#3498DB"

QUOTES = [
    "The secret of getting ahead is getting started.",
    "It always seems impossible until it's done.",
    "Don't watch the clock; do what it does. Keep going.",
    "Focus on being productive instead of busy.",
    "Small steps every day add up to big results.",
    "Your future is created by what you do today, not tomorrow.",
    "Believe you can and you're halfway there.",
    "Action is the foundational key to all success."
]

def prepare_resources():
    if os.path.exists(ICON_ICO) and not os.path.exists(ICON_PNG):
        try:
            img = Image.open(ICON_ICO)
            img.save(ICON_PNG, format="PNG")
        except Exception as e:
            pass
            
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=["date", "task", "subnotes", "status"])
        df.to_csv(DB_FILE, index=False)

prepare_resources()
df = pd.read_csv(DB_FILE)
df.fillna("", inplace=True)
df['task'] = df['task'].astype(str)
df['subnotes'] = df['subnotes'].astype(str)
df['status'] = df['status'].astype(str)

today_str = str(date.today())

# Removed random.seed() so the quote changes on every single refresh!
daily_quote = random.choice(QUOTES)

# --- APP UI SETUP & CUSTOM CSS ---
st.set_page_config(page_title="RRS Daily Task", page_icon=ICON_ICO if os.path.exists(ICON_ICO) else "📝", layout="wide")

st.markdown(f"""
    <style>
    .stApp {{ background-color: #F4F7F6; }}
    .main-header {{ color: #2C3E50; font-family: 'Helvetica Neue', sans-serif; font-weight: bold; }}
    .quote-box {{ background-color: #EBF5FB; padding: 20px; border-left: 6px solid {THEME_COLOR}; border-radius: 8px; font-style: italic; margin-bottom: 25px; color: #555; font-size: 1.1em; }}
    </style>
""", unsafe_allow_html=True)

# --- HEADER SECTION ---
col1, col2 = st.columns([1, 5])
with col1:
    if os.path.exists(ICON_PNG):
        st.image(ICON_PNG, width=90)
with col2:
    st.markdown("<h1 class='main-header'>RRS Daily Task</h1>", unsafe_allow_html=True)
    st.write(f"**Date:** {date.today().strftime('%B %d, %Y')}")

st.markdown(f"<div class='quote-box'>“{daily_quote}”</div>", unsafe_allow_html=True)

# --- MORNING SECTION ---
st.subheader("☀️ Morning Prep: Manage Tasks")

with st.expander("➕ Add New Task", expanded=True):
    with st.form("add_task_form", clear_on_submit=True):
        new_task = st.text_input("Main Task:", placeholder="e.g., Finish project report...")
        new_subnotes = st.text_area("Subnotes (Optional):", height=68)
        if st.form_submit_button("Add to Today's List") and new_task.strip() != "":
            new_row = pd.DataFrame([{"date": today_str, "task": new_task.strip(), "subnotes": new_subnotes.strip(), "status": "pending"}])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(DB_FILE, index=False)
            st.rerun()

pending_df = df[df['status'] == 'pending'].copy()

if not pending_df.empty:
    edited_df = st.data_editor(
        pending_df[['task', 'subnotes', 'status']],
        column_config={
            "status": st.column_config.SelectboxColumn("Status", options=["pending", "closed"], required=True),
            "task": st.column_config.TextColumn("Task", required=True),
            "subnotes": st.column_config.TextColumn("Subnotes")
        },
        hide_index=True, num_rows="dynamic", use_container_width=True, key="task_editor"
    )

    if st.button("💾 Save Changes"):
        df = df[df['status'] != 'pending']
        edited_df['date'] = today_str
        df = pd.concat([df, edited_df], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        st.success("Changes Saved!")
        st.rerun()

    st.divider()

    if st.button("🖨️ Generate 2-Column PDF"):
        latest_pending = df[df['status'] == 'pending']
        
        class StylishPDF(FPDF):
            def header(self):
                self.set_fill_color(52, 152, 219)
                self.rect(0, 0, 210, 35, 'F')
                if os.path.exists(ICON_PNG):
                    self.image(ICON_PNG, x=10, y=5, w=25)
                self.set_font('Helvetica', 'B', 24)
                self.set_text_color(255, 255, 255)
                self.cell(80)
                self.cell(100, 15, 'RRS Daily Task', 0, 1, 'R')
                self.set_font('Helvetica', '', 14)
                self.cell(180, 10, date.today().strftime('%B %d, %Y'), 0, 1, 'R')
                self.ln(10)

        pdf = StylishPDF()
        pdf.add_page()
        pdf.set_text_color(50, 50, 50)
        
        pdf.set_fill_color(235, 245, 251)
        pdf.rect(10, pdf.get_y(), 190, 20, 'F')
        pdf.set_font("Helvetica", 'I', 12)
        pdf.set_xy(15, pdf.get_y() + 5)
        pdf.multi_cell(180, 10, txt=f'"{daily_quote}"', align='C')
        pdf.ln(15)
        
        pdf.set_font("Helvetica", 'B', 16)
        pdf.set_text_color(52, 152, 219)
        pdf.cell(0, 10, "Today's Priorities", ln=True)
        pdf.set_text_color(50, 50, 50)
        
        y_cursor = pdf.get_y()
        for i in range(0, len(latest_pending), 2):
            task1 = latest_pending.iloc[i]
            task2 = latest_pending.iloc[i+1] if i+1 < len(latest_pending) else None
            
            pdf.set_xy(10, y_cursor)
            pdf.set_font('zapfdingbats', '', 14)
            pdf.cell(8, 8, 'o', 0, 0)
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(85, 8, txt=task1['task'], border=0, ln=0)
            
            if task2 is not None:
                pdf.set_xy(105, y_cursor)
                pdf.set_font('zapfdingbats', '', 14)
                pdf.cell(8, 8, 'o', 0, 0)
                pdf.set_font('Helvetica', 'B', 12)
                pdf.cell(85, 8, txt=task2['task'], border=0, ln=0)
            
            pdf.ln(8)
            y_subnotes = pdf.get_y()
            max_y = y_subnotes
            
            if pd.notna(task1['subnotes']) and task1['subnotes'] != "":
                pdf.set_xy(18, y_subnotes)
                pdf.set_font('Helvetica', 'I', 10)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(80, 5, task1['subnotes'])
                max_y = max(max_y, pdf.get_y())
                
            if task2 is not None and pd.notna(task2['subnotes']) and task2['subnotes'] != "":
                pdf.set_xy(113, y_subnotes)
                pdf.set_font('Helvetica', 'I', 10)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(80, 5, task2['subnotes'])
                max_y = max(max_y, pdf.get_y())
                
            pdf.set_text_color(50, 50, 50)
            y_cursor = max_y + 4
            pdf.set_y(y_cursor)
            
        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 16)
        pdf.set_text_color(52, 152, 219)
        pdf.cell(0, 10, txt="Incoming Tasks & Notes:", ln=True)
        pdf.set_draw_color(200, 200, 200)
        for _ in range(4):
            pdf.ln(12)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())

        # Removed the Gratitude Box logic entirely

        pdf_name = "daily_focus.pdf"
        pdf.output(pdf_name)
        with open(pdf_name, "rb") as f:
            st.download_button("📥 Download PDF", f, file_name=f"RRS_Task_{today_str}.pdf", mime="application/pdf")

st.divider()

# --- EVENING SECTION ---
st.subheader("🌙 Evening Sync")
uploaded_file = st.file_uploader("Take a photo of your page", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    image = Image.open(uploaded_file)
    img_array = np.array(image)
    st.image(image, caption="Analyzing...", width=300)
    
    @st.cache_resource
    def load_reader(): return easyocr.Reader(['en'])
    reader = load_reader()
    results = reader.readtext(img_array)
    
    found_handwriting = []
    ignore_words = ["rrs", "daily", "task", "date", "priorities", "incoming", "notes"]
    latest_pending = df[df['status'] == 'pending']
    
    for (bbox, text, prob) in results:
        is_template = any(word in text.lower() for word in ignore_words)
        is_existing = any(text.lower() in existing_task.lower() for existing_task in latest_pending['task'].tolist())
        if prob > 0.4 and not is_template and not is_existing and len(text) > 3:
            found_handwriting.append(text)

    with st.form("sync_form"):
        approved_new_tasks = []
        if not found_handwriting:
            st.write("*No new handwriting detected clearly.*")
        else:
            for i, hw_task in enumerate(found_handwriting):
                col1, col2 = st.columns([3, 1])
                edited_task = col1.text_input(f"Note {i+1}", value=hw_task, key=f"hw_{i}", label_visibility="collapsed")
                if col2.checkbox("Add", value=True, key=f"add_{i}"):
                    approved_new_tasks.append(edited_task)
                
        if st.form_submit_button("🚀 Add Notes & Close Day"):
            for new_t in approved_new_tasks:
                if new_t.strip() != "":
                    new_row = pd.DataFrame([{"date": today_str, "task": new_t.strip(), "subnotes": "", "status": "pending"}])
                    df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(DB_FILE, index=False)
            st.success("Notes added! List updated for tomorrow.")
            st.rerun()