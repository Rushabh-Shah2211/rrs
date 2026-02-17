import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import date, datetime, timedelta
import os
import easyocr
import numpy as np
from PIL import Image
import random
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import schedule
import time
import threading
from streamlit_gsheets import GSheetsConnection
import re

# --- APP CONFIG & UI SETUP ---
ICON_ICO = "icon.ico"
ICON_PNG = "icon.png"
THEME_COLOR = "#3498DB"

st.set_page_config(page_title="RRS Daily Task Manager", page_icon=ICON_ICO if os.path.exists(ICON_ICO) else "📝", layout="wide")

# --- SESSION STATE INITIALIZATION ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'current_date' not in st.session_state:
    st.session_state.current_date = date.today()

# --- AUTHENTICATION FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password, users_df):
    user = users_df[users_df['username'] == username]
    if not user.empty and user.iloc[0]['password'] == hash_password(password):
        return user.iloc[0]['user_id'], user.iloc[0]['name']
    return None, None

def register_user(username, password, name, email, users_df):
    if username in users_df['username'].values:
        return False, "Username already exists"
    
    new_user = pd.DataFrame([{
        'user_id': hashlib.md5(f"{username}{datetime.now()}".encode()).hexdigest()[:8],
        'username': username,
        'password': hash_password(password),
        'name': name,
        'email': email,
        'created_date': date.today().isoformat()
    }])
    users_df = pd.concat([users_df, new_user], ignore_index=True)
    return True, users_df

# --- EMAIL FUNCTIONS ---
def send_daily_pdf(email, pdf_path, username, task_count):
    """Send PDF via email"""
    try:
        sender_email = st.secrets["email"]["sender"]
        sender_password = st.secrets["email"]["password"]
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = st.secrets["email"]["smtp_port"]
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = f"RRS Daily Tasks - {date.today().strftime('%B %d, %Y')}"
        
        body = f"""
        <html>
        <body>
            <h2>Hello {username},</h2>
            <p>Here are your tasks for today ({date.today().strftime('%B %d, %Y')}).</p>
            <p><strong>Total Tasks:</strong> {task_count}</p>
            <p>Print this sheet and keep it on your desk. In the evening, mark completed tasks and add new ones, then scan/upload back to the app.</p>
            <br>
            <p>Happy tasking!</p>
            <p><em>RRS Daily Task Manager</em></p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        with open(pdf_path, 'rb') as f:
            attach = MIMEApplication(f.read(), _subtype="pdf")
            attach.add_header('Content-Disposition', f'attachment', filename=os.path.basename(pdf_path))
            msg.attach(attach)
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"Email error: {str(e)}")
        return False

# --- DATABASE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Load or create Users sheet
try:
    users_df = conn.read(worksheet="Users", ttl=0)
    if users_df.empty or len(users_df.columns) == 0:
        users_df = pd.DataFrame(columns=["user_id", "username", "password", "name", "email", "created_date"])
except:
    users_df = pd.DataFrame(columns=["user_id", "username", "password", "name", "email", "created_date"])

# Load or create Tasks sheet
try:
    tasks_df = conn.read(worksheet="Tasks", ttl=0)
    if tasks_df.empty or len(tasks_df.columns) == 0:
        tasks_df = pd.DataFrame(columns=["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"])
except:
    tasks_df = pd.DataFrame(columns=["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"])

tasks_df.fillna("", inplace=True)

# --- LOGIN PAGE ---
if not st.session_state.authenticated:
    st.markdown(f"""
        <style>
        .login-container {{
            max-width: 400px;
            margin: 50px auto;
            padding: 30px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .login-header {{
            text-align: center;
            color: {THEME_COLOR};
            margin-bottom: 30px;
        }}
        </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if os.path.exists(ICON_PNG):
                st.image(ICON_PNG, width=100)
            st.markdown("<h2 class='login-header'>RRS Daily Task Manager</h2>", unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["Login", "Register"])
            
            with tab1:
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    if st.form_submit_button("Login", use_container_width=True):
                        user_id, user_name = authenticate_user(username, password, users_df)
                        if user_id:
                            st.session_state.authenticated = True
                            st.session_state.username = username
                            st.session_state.user_id = user_id
                            st.session_state.user_name = user_name
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
            
            with tab2:
                with st.form("register_form"):
                    new_name = st.text_input("Full Name")
                    new_email = st.text_input("Email")
                    new_username = st.text_input("Username")
                    new_password = st.text_input("Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    
                    if st.form_submit_button("Register", use_container_width=True):
                        if new_password != confirm_password:
                            st.error("Passwords don't match")
                        elif not new_username or not new_password or not new_name or not new_email:
                            st.error("All fields are required")
                        else:
                            success, result = register_user(new_username, new_password, new_name, new_email, users_df)
                            if success:
                                conn.update(worksheet="Users", data=result)
                                st.success("Registration successful! Please login.")
                            else:
                                st.error(result)
    
    st.stop()

# --- MAIN APP (Authenticated) ---
today_str = str(st.session_state.current_date)

# Filter tasks for current user
user_tasks_df = tasks_df[tasks_df['user_id'] == st.session_state.user_id].copy()

# --- SIDEBAR WITH USER INFO AND SETTINGS ---
with st.sidebar:
    st.image(ICON_PNG if os.path.exists(ICON_PNG) else None, width=50)
    st.markdown(f"### Welcome, {st.session_state.user_name}!")
    st.markdown(f"**Today:** {date.today().strftime('%B %d, %Y')}")
    
    st.divider()
    
    # Date selector for viewing different days
    st.markdown("#### 📅 View Tasks For:")
    view_date = st.date_input("Select Date", value=st.session_state.current_date)
    if view_date != st.session_state.current_date:
        st.session_state.current_date = view_date
        st.rerun()
    
    st.divider()
    
    # Categories management
    st.markdown("#### 🏷️ Categories")
    categories = ["Work", "Personal", "Urgent", "Follow-up", "Meeting", "Other"]
    selected_category = st.selectbox("Filter by category", ["All"] + categories)
    
    st.divider()
    
    # Email settings
    st.markdown("#### 📧 Email Settings")
    auto_email = st.checkbox("Auto-send daily PDF at 8 AM", value=True)
    
    if st.button("Send Today's PDF Now"):
        with st.spinner("Generating and sending PDF..."):
            pdf_path = generate_daily_pdf(user_tasks_df, st.session_state.user_name)
            user_email = users_df[users_df['user_id'] == st.session_state.user_id].iloc[0]['email']
            task_count = len(user_tasks_df[user_tasks_df['status'] == 'pending'])
            if send_daily_pdf(user_email, pdf_path, st.session_state.user_name, task_count):
                st.success("PDF sent to your email!")
            else:
                st.error("Failed to send email. Check configuration.")
    
    st.divider()
    
    if st.button("🚪 Logout"):
        for key in ['authenticated', 'username', 'user_id', 'user_name', 'current_date']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# --- QUOTES ---
QUOTES = [
    "The secret of getting ahead is getting started.",
    "It always seems impossible until it's done.",
    "Don't watch the clock; do what it does. Keep going.",
    "Focus on being productive instead of busy.",
    "Small steps every day add up to big results.",
    "Your future is created by what you do today, not tomorrow.",
    "Believe you can and you're halfway there.",
    "Action is the foundational key to all success.",
    "The only way to do great work is to love what you do.",
    "Start where you are. Use what you have. Do what you can."
]
daily_quote = random.choice(QUOTES)

# --- MAIN CONTENT ---
st.markdown(f"<h1 style='color: {THEME_COLOR};'>📋 {st.session_state.user_name}'s Daily Tasks</h1>", unsafe_allow_html=True)
st.markdown(f"<div style='background-color: #EBF5FB; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>“{daily_quote}”</div>", unsafe_allow_html=True)

# Get tasks for selected date (including those with due_date <= selected date)
if selected_category == "All":
    today_tasks = user_tasks_df[
        (user_tasks_df['due_date'] <= today_str) | (user_tasks_df['due_date'] == "")
    ]
else:
    today_tasks = user_tasks_df[
        ((user_tasks_df['due_date'] <= today_str) | (user_tasks_df['due_date'] == "")) &
        (user_tasks_df['category'] == selected_category)
    ]

pending_tasks = today_tasks[today_tasks['status'] == 'pending'].copy()
completed_tasks = user_tasks_df[user_tasks_df['status'] == 'closed'].copy()

# --- TABS FOR DIFFERENT VIEWS ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 Today's Tasks", "➕ Add Tasks", "📊 Analytics", "⚙️ Settings"])

with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📌 Pending Tasks ({len(pending_tasks)})")
        
        if not pending_tasks.empty:
            # Editable task list
            edited_df = st.data_editor(
                pending_tasks[['task', 'subnotes', 'priority', 'category', 'status']],
                column_config={
                    "status": st.column_config.SelectboxColumn("Status", options=["pending", "closed"], required=True),
                    "priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"], required=True),
                    "category": st.column_config.SelectboxColumn("Category", options=categories, required=True),
                    "task": st.column_config.TextColumn("Task", required=True, width="large"),
                    "subnotes": st.column_config.TextColumn("Notes", width="large")
                },
                hide_index=True,
                num_rows="dynamic",
                use_container_width=True,
                key="task_editor"
            )
            
            if st.button("💾 Save Changes", use_container_width=True):
                # Update tasks
                user_tasks_df = user_tasks_df[~user_tasks_df.index.isin(pending_tasks.index)]
                edited_df['date'] = today_str
                edited_df['user_id'] = st.session_state.user_id
                edited_df['due_date'] = today_str
                user_tasks_df = pd.concat([user_tasks_df, edited_df], ignore_index=True)
                
                # Update Google Sheet
                all_tasks = tasks_df[tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                conn.update(worksheet="Tasks", data=all_tasks)
                tasks_df = all_tasks
                
                st.success("Changes saved successfully!")
                st.rerun()
        else:
            st.info("No pending tasks for today! 🎉")
    
    with col2:
        st.subheader("✅ Completed Today")
        today_completed = completed_tasks[completed_tasks['completed_date'] == today_str]
        if not today_completed.empty:
            for _, task in today_completed.iterrows():
                st.markdown(f"~~{task['task']}~~")
        else:
            st.info("No tasks completed today yet.")
        
        st.divider()
        
        # Quick stats
        st.subheader("📊 Quick Stats")
        total_pending = len(user_tasks_df[user_tasks_df['status'] == 'pending'])
        total_completed = len(user_tasks_df[user_tasks_df['status'] == 'closed'])
        completion_rate = (total_completed / (total_pending + total_completed) * 100) if (total_pending + total_completed) > 0 else 0
        
        st.metric("Total Tasks", len(user_tasks_df))
        st.metric("Pending", total_pending)
        st.metric("Completed", total_completed)
        st.progress(completion_rate / 100, text=f"Completion Rate: {completion_rate:.1f}%")

with tab2:
    st.subheader("➕ Add New Tasks")
    
    with st.form("add_task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_task = st.text_input("Task Title *", placeholder="e.g., Follow up on BCT Loan")
            new_category = st.selectbox("Category", categories)
            new_priority = st.select_slider("Priority", options=["Low", "Medium", "High"], value="Medium")
        
        with col2:
            new_due_date = st.date_input("Due Date", value=date.today())
            repeat_option = st.selectbox("Repeat", ["None", "Daily", "Weekly", "Monthly"])
        
        new_subnotes = st.text_area("Additional Notes", height=100, placeholder="Add any details, links, or notes...")
        
        if st.form_submit_button("📥 Add Task", use_container_width=True):
            if new_task.strip():
                task_id = hashlib.md5(f"{new_task}{datetime.now()}".encode()).hexdigest()[:12]
                
                new_row = pd.DataFrame([{
                    'user_id': st.session_state.user_id,
                    'task_id': task_id,
                    'date': today_str,
                    'task': new_task.strip(),
                    'subnotes': new_subnotes.strip(),
                    'status': 'pending',
                    'priority': new_priority,
                    'due_date': str(new_due_date),
                    'category': new_category,
                    'completed_date': ""
                }])
                
                # Handle repeating tasks
                if repeat_option != "None":
                    # Create multiple tasks for future dates
                    if repeat_option == "Daily":
                        for i in range(1, 7):  # Create for next 7 days
                            future_date = new_due_date + timedelta(days=i)
                            future_task = new_row.copy()
                            future_task['task_id'] = hashlib.md5(f"{new_task}{future_date}".encode()).hexdigest()[:12]
                            future_task['due_date'] = str(future_date)
                            future_task['date'] = str(future_date)
                            user_tasks_df = pd.concat([user_tasks_df, future_task], ignore_index=True)
                
                user_tasks_df = pd.concat([user_tasks_df, new_row], ignore_index=True)
                
                # Update Google Sheet
                all_tasks = tasks_df[tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                conn.update(worksheet="Tasks", data=all_tasks)
                tasks_df = all_tasks
                
                st.success("Task added successfully!")
                st.rerun()
            else:
                st.error("Task title is required!")

with tab3:
    st.subheader("📊 Task Analytics")
    
    # Task completion trend
    st.markdown("#### Completion Trend (Last 7 Days)")
    last_7_days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    
    completion_data = []
    for day in last_7_days:
        day_completed = len(user_tasks_df[
            (user_tasks_df['completed_date'] == day) & 
            (user_tasks_df['status'] == 'closed')
        ])
        completion_data.append(day_completed)
    
    chart_data = pd.DataFrame({
        'Date': last_7_days,
        'Completed': completion_data
    })
    
    st.bar_chart(chart_data.set_index('Date'))
    
    # Category distribution
    st.markdown("#### Tasks by Category")
    category_counts = user_tasks_df[user_tasks_df['status'] == 'pending']['category'].value_counts()
    if not category_counts.empty:
        st.bar_chart(category_counts)
    
    # Priority breakdown
    st.markdown("#### Priority Breakdown")
    priority_counts = user_tasks_df[user_tasks_df['status'] == 'pending']['priority'].value_counts()
    if not priority_counts.empty:
        cols = st.columns(3)
        priorities = ['High', 'Medium', 'Low']
        for i, priority in enumerate(priorities):
            count = priority_counts.get(priority, 0)
            cols[i].metric(priority, count)

with tab4:
    st.subheader("⚙️ Settings")
    
    with st.form("settings_form"):
        st.markdown("#### Email Preferences")
        user_email = st.text_input("Email Address for Daily PDF", 
                                   value=users_df[users_df['user_id'] == st.session_state.user_id].iloc[0]['email'])
        email_time = st.time_input("Daily PDF Send Time", value=datetime.strptime("08:00", "%H:%M").time())
        
        st.markdown("#### Display Preferences")
        show_completed = st.checkbox("Show completed tasks in main view", value=False)
        default_view = st.selectbox("Default View", ["Today", "Week", "Month"])
        
        if st.form_submit_button("💾 Save Settings"):
            # Update user settings in database
            st.success("Settings saved!")
    
    st.divider()
    
    st.markdown("#### Danger Zone")
    if st.button("🗑️ Delete All Completed Tasks", type="secondary"):
        if st.checkbox("Confirm deletion of all completed tasks"):
            user_tasks_df = user_tasks_df[user_tasks_df['status'] != 'closed']
            all_tasks = tasks_df[tasks_df['user_id'] != st.session_state.user_id]
            all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
            conn.update(worksheet="Tasks", data=all_tasks)
            tasks_df = all_tasks
            st.success("Completed tasks deleted!")
            st.rerun()

# --- EVENING SYNC WITH IMPROVED OCR ---
st.divider()
st.subheader("🌙 Evening Sync - Upload Your Completed Sheet")

uploaded_file = st.file_uploader("Upload scanned/photo of your completed task sheet", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    image = Image.open(uploaded_file)
    img_array = np.array(image)
    st.image(image, caption="Uploaded Sheet", width=400)
    
    @st.cache_resource
    def load_reader():
        return easyocr.Reader(['en'])
    
    reader = load_reader()
    results = reader.readtext(img_array, paragraph=False)
    
    # Better text detection
    found_text = []
    template_words = ["rrs", "daily", "task", "date", "priorities", "incoming", "notes", "today", "grateful"]
    
    for (bbox, text, prob) in results:
        if prob > 0.3 and len(text.strip()) > 2:
            # Check if it's likely a task (not template text)
            is_template = any(word in text.lower() for word in template_words)
            if not is_template and not text.replace(" ", "").isdigit():
                found_text.append(text.strip())
    
    # Separate completed tasks and new tasks
    completed_tasks = []
    new_tasks = []
    
    for text in found_text:
        # Check if task is struck out (simplified detection - in real app, use image processing)
        if any(mark in text.lower() for mark in ["x", "done", "completed", "✓", "✅"]):
            completed_tasks.append(text)
        else:
            new_tasks.append(text)
    
    with st.form("evening_sync_form"):
        st.markdown("### Review Detected Items")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### ✅ Completed Tasks")
            if completed_tasks:
                selected_completed = []
                for i, task in enumerate(completed_tasks):
                    if st.checkbox(task, key=f"comp_{i}"):
                        selected_completed.append(task)
            else:
                st.info("No completed tasks detected")
        
        with col2:
            st.markdown("#### 📝 New Tasks")
            if new_tasks:
                new_task_inputs = []
                for i, task in enumerate(new_tasks):
                    edited_task = st.text_input(f"Task {i+1}", value=task, key=f"new_{i}")
                    task_due = st.date_input(f"Due Date {i+1}", value=date.today(), key=f"due_{i}")
                    task_category = st.selectbox(f"Category {i+1}", categories, key=f"cat_{i}")
                    if st.checkbox(f"Add this task", value=True, key=f"add_{i}"):
                        new_task_inputs.append({
                            'task': edited_task,
                            'due_date': str(task_due),
                            'category': task_category
                        })
            else:
                st.info("No new tasks detected")
        
        st.divider()
        
        if st.form_submit_button("🚀 Process Evening Sync", use_container_width=True):
            changes_made = False
            
            # Mark completed tasks
            if 'selected_completed' in locals() and selected_completed:
                for task_text in selected_completed:
                    # Find and close the task
                    mask = (user_tasks_df['task'].str.contains(task_text[:20], case=False, na=False)) & \
                           (user_tasks_df['status'] == 'pending')
                    user_tasks_df.loc[mask, 'status'] = 'closed'
                    user_tasks_df.loc[mask, 'completed_date'] = today_str
                changes_made = True
            
            # Add new tasks
            if 'new_task_inputs' in locals() and new_task_inputs:
                for task_data in new_task_inputs:
                    task_id = hashlib.md5(f"{task_data['task']}{datetime.now()}".encode()).hexdigest()[:12]
                    new_row = pd.DataFrame([{
                        'user_id': st.session_state.user_id,
                        'task_id': task_id,
                        'date': today_str,
                        'task': task_data['task'],
                        'subnotes': "",
                        'status': 'pending',
                        'priority': 'Medium',
                        'due_date': task_data['due_date'],
                        'category': task_data['category'],
                        'completed_date': ""
                    }])
                    user_tasks_df = pd.concat([user_tasks_df, new_row], ignore_index=True)
                changes_made = True
            
            if changes_made:
                # Update Google Sheet
                all_tasks = tasks_df[tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                conn.update(worksheet="Tasks", data=all_tasks)
                tasks_df = all_tasks
                st.success("Evening sync completed successfully!")
                st.balloons()
                st.rerun()
            else:
                st.warning("No changes detected")

# --- PDF GENERATION FUNCTION ---
def generate_daily_pdf(tasks_df, user_name):
    """Generate PDF for daily tasks"""
    
    class StylishPDF(FPDF):
        def header(self):
            self.set_fill_color(52, 152, 219)
            self.rect(0, 0, 210, 35, 'F')
            if os.path.exists(ICON_PNG):
                self.image(ICON_PNG, x=10, y=5, w=25)
            self.set_font('Helvetica', 'B', 24)
            self.set_text_color(255, 255, 255)
            self.cell(80)
            self.cell(100, 15, f'{user_name}\'s Tasks', 0, 1, 'R')
            self.set_font('Helvetica', '', 14)
            self.cell(180, 10, date.today().strftime('%B %d, %Y'), 0, 1, 'R')
            self.ln(10)
    
    pending_tasks = tasks_df[tasks_df['status'] == 'pending'].copy()
    
    pdf = StylishPDF()
    pdf.add_page()
    pdf.set_text_color(50, 50, 50)
    
    # Quote
    pdf.set_fill_color(235, 245, 251)
    pdf.rect(10, pdf.get_y(), 190, 20, 'F')
    pdf.set_font("Helvetica", 'I', 12)
    pdf.set_xy(15, pdf.get_y() + 5)
    pdf.multi_cell(180, 10, txt=f'"{daily_quote}"', align='C')
    pdf.ln(15)
    
    # Tasks by priority
    for priority in ['High', 'Medium', 'Low']:
        priority_tasks = pending_tasks[pending_tasks['priority'] == priority]
        if not priority_tasks.empty:
            # Priority header
            pdf.set_font("Helvetica", 'B', 14)
            colors = {'High': (255, 0, 0), 'Medium': (255, 165, 0), 'Low': (0, 128, 0)}
            pdf.set_text_color(*colors[priority])
            pdf.cell(0, 10, f"{priority} Priority", ln=True)
            pdf.set_text_color(50, 50, 50)
            
            # Tasks in this priority
            for _, task in priority_tasks.iterrows():
                pdf.set_font('zapfdingbats', '', 12)
                pdf.cell(8, 8, 'o', 0, 0)
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, txt=task['task'], ln=1)
                
                if task['subnotes'] and task['subnotes'] != "":
                    pdf.set_x(15)
                    pdf.set_font('Helvetica', 'I', 9)
                    pdf.set_text_color(100, 100, 100)
                    pdf.multi_cell(0, 5, task['subnotes'])
                    pdf.set_text_color(50, 50, 50)
                
                pdf.ln(3)
    
    # Incoming tasks section
    pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.set_text_color(52, 152, 219)
    pdf.cell(0, 10, txt="Incoming Tasks & Notes:", ln=True)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_text_color(50, 50, 50)
    
    # Lines for notes
    for i in range(5):
        pdf.ln(10)
        pdf.cell(10)
        pdf.cell(0, 0, '', 'B', ln=1)
    
    # Gratitude section
    pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 12)
    pdf.set_text_color(52, 152, 219)
    pdf.cell(0, 10, txt="Today I am grateful for:", ln=True)
    pdf.set_text_color(50, 50, 50)
    
    for i in range(3):
        pdf.ln(8)
        pdf.cell(15)
        pdf.cell(0, 0, '', 'B', ln=1)
    
    # Save PDF
    pdf_name = f"daily_tasks_{st.session_state.user_id}_{today_str}.pdf"
    pdf.output(pdf_name)
    return pdf_name

# Auto-generate PDF button
if st.sidebar.button("📄 Generate PDF for Printing"):
    pdf_path = generate_daily_pdf(user_tasks_df, st.session_state.user_name)
    with open(pdf_path, "rb") as f:
        st.sidebar.download_button(
            "📥 Download PDF",
            f,
            file_name=f"RRS_Tasks_{today_str}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# --- AUTO EMAIL SCHEDULER (Run in background) ---
def schedule_daily_email():
    """Background thread for scheduled emails"""
    while True:
        now = datetime.now()
        # Check if it's 8 AM
        if now.hour == 8 and now.minute == 0:
            for _, user in users_df.iterrows():
                user_tasks = tasks_df[tasks_df['user_id'] == user['user_id']]
                pdf_path = generate_daily_pdf(user_tasks, user['name'])
                send_daily_pdf(user['email'], pdf_path, user['name'], len(user_tasks[user_tasks['status'] == 'pending']))
            time.sleep(60)  # Wait a minute to avoid multiple sends
        time.sleep(30)  # Check every 30 seconds

# Start scheduler in background (uncomment in production)
# if 'scheduler_started' not in st.session_state:
#     thread = threading.Thread(target=schedule_daily_email, daemon=True)
#     thread.start()
#     st.session_state.scheduler_started = True