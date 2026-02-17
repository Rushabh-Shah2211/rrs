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
import time
import re
from streamlit_gsheets import GSheetsConnection
import gspread
from gspread.exceptions import WorksheetNotFound

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
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'current_date' not in st.session_state:
    st.session_state.current_date = date.today()
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False
if 'users_df' not in st.session_state:
    st.session_state.users_df = None
if 'tasks_df' not in st.session_state:
    st.session_state.tasks_df = None

# --- HELPER FUNCTIONS (DEFINED FIRST) ---

def calculate_streak(tasks_df):
    """Calculate current completion streak"""
    try:
        if tasks_df is None or tasks_df.empty or 'completed_date' not in tasks_df.columns:
            return 0
        
        completed_dates = tasks_df[tasks_df['completed_date'] != ""]['completed_date'].unique()
        if len(completed_dates) == 0:
            return 0
        
        try:
            completed_dates = sorted([datetime.strptime(d, '%Y-%m-%d').date() for d in completed_dates], reverse=True)
            
            streak = 0
            current_date = date.today()
            
            while current_date in completed_dates:
                streak += 1
                current_date -= timedelta(days=1)
            
            return streak
        except:
            return 0
    except:
        return 0

def generate_daily_pdf(tasks_df, user_name, daily_quote):
    """Generate PDF for daily tasks"""
    try:
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
        
        pending_tasks = tasks_df[tasks_df['status'] == 'pending'].copy() if tasks_df is not None and not tasks_df.empty else pd.DataFrame()
        
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
        pdf.set_font("Helvetica", 'B', 16)
        pdf.set_text_color(52, 152, 219)
        pdf.cell(0, 10, "Today's Priorities", ln=True)
        pdf.set_text_color(50, 50, 50)
        
        if not pending_tasks.empty:
            # Sort by priority if column exists
            if 'priority' in pending_tasks.columns:
                priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
                pending_tasks['priority_order'] = pending_tasks['priority'].map(priority_order)
                pending_tasks = pending_tasks.sort_values('priority_order')
            
            for priority in ['High', 'Medium', 'Low']:
                if 'priority' in pending_tasks.columns:
                    priority_tasks = pending_tasks[pending_tasks['priority'] == priority]
                else:
                    priority_tasks = pending_tasks
                
                if not priority_tasks.empty:
                    # Priority header
                    pdf.set_font("Helvetica", 'B', 12)
                    priority_colors = {'High': (255, 0, 0), 'Medium': (255, 165, 0), 'Low': (0, 128, 0)}
                    pdf.set_text_color(*priority_colors.get(priority, (50, 50, 50)))
                    pdf.cell(0, 8, f"{priority} Priority" if 'priority' in pending_tasks.columns else "Tasks", ln=True)
                    pdf.set_text_color(50, 50, 50)
                    
                    # Tasks
                    for _, task in priority_tasks.iterrows():
                        # Checkbox
                        pdf.set_font('zapfdingbats', '', 12)
                        pdf.cell(8, 8, 'o', 0, 0)
                        
                        # Task title
                        pdf.set_font('Helvetica', 'B', 11)
                        pdf.set_x(18)
                        pdf.cell(0, 8, task['task'] if 'task' in task else "Untitled", ln=1)
                        
                        # Subnotes
                        if task.get('subnotes') and task['subnotes'] != "":
                            pdf.set_x(18)
                            pdf.set_font('Helvetica', 'I', 9)
                            pdf.set_text_color(100, 100, 100)
                            pdf.multi_cell(0, 4, task['subnotes'])
                            pdf.set_text_color(50, 50, 50)
                        
                        pdf.ln(2)
                    
                    pdf.ln(5)
        else:
            pdf.set_font("Helvetica", '', 12)
            pdf.cell(0, 10, "No pending tasks for today!", ln=True)
        
        # Incoming tasks section
        pdf.ln(5)
        pdf.set_font("Helvetica", 'B', 14)
        pdf.set_text_color(52, 152, 219)
        pdf.cell(0, 10, "Incoming Tasks & Notes:", ln=True)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_text_color(50, 50, 50)
        
        # Lines for notes
        for i in range(5):
            pdf.ln(8)
            pdf.cell(10)
            pdf.cell(0, 0, '', 'B', ln=1)
        
        # Gratitude section
        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 12)
        pdf.set_text_color(52, 152, 219)
        pdf.cell(0, 8, "Today I am grateful for:", ln=True)
        pdf.set_text_color(50, 50, 50)
        
        for i in range(3):
            pdf.ln(8)
            pdf.cell(15)
            pdf.cell(0, 0, '', 'B', ln=1)
        
        # Save PDF
        pdf_path = f"daily_tasks_{st.session_state.user_id}_{date.today().strftime('%Y%m%d')}.pdf"
        pdf.output(pdf_path)
        return pdf_path
    except Exception as e:
        st.error(f"PDF generation error: {str(e)}")
        return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password, users_df):
    try:
        if users_df is None or users_df.empty or 'username' not in users_df.columns:
            return None, None
        user = users_df[users_df['username'] == username]
        if not user.empty and user.iloc[0]['password'] == hash_password(password):
            return user.iloc[0]['user_id'], user.iloc[0]['name']
        return None, None
    except:
        return None, None

def register_user(username, password, name, email, users_df):
    try:
        if users_df is not None and 'username' in users_df.columns and username in users_df['username'].values:
            return False, "Username already exists"
        
        new_user = pd.DataFrame([{
            'user_id': hashlib.md5(f"{username}{datetime.now()}".encode()).hexdigest()[:8],
            'username': username,
            'password': hash_password(password),
            'name': name,
            'email': email,
            'created_date': date.today().isoformat()
        }])
        
        if users_df is None or users_df.empty:
            users_df = new_user
        else:
            users_df = pd.concat([users_df, new_user], ignore_index=True)
        
        return True, users_df
    except Exception as e:
        return False, f"Registration error: {str(e)}"

def send_daily_pdf(email, pdf_path, username, task_count):
    """Send PDF via email"""
    try:
        if 'email' not in st.secrets:
            st.warning("Email not configured. Please add email settings to .streamlit/secrets.toml")
            return False
            
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
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #3498DB; padding: 20px; color: white; text-align: center;">
                <h2>RRS Daily Task Manager</h2>
            </div>
            <div style="padding: 20px;">
                <h3>Hello {username},</h3>
                <p>Here are your tasks for today ({date.today().strftime('%B %d, %Y')}).</p>
                <p><strong>Total Tasks:</strong> {task_count}</p>
                <p>Print this sheet and keep it on your desk. In the evening, mark completed tasks and add new ones, then scan/upload back to the app.</p>
                <hr>
                <p style="color: #666;">Happy tasking!</p>
                <p><em>RRS Daily Task Manager</em></p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        with open(pdf_path, 'rb') as f:
            attach = MIMEApplication(f.read(), _subtype="pdf")
            attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(pdf_path))
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

def get_user_tasks(tasks_df, user_id):
    """Safely get tasks for a specific user"""
    try:
        if tasks_df is None or tasks_df.empty:
            return pd.DataFrame(columns=["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"])
        
        if 'user_id' not in tasks_df.columns:
            tasks_df['user_id'] = ""
            if 'conn' in st.session_state:
                st.session_state.conn.update(worksheet="Tasks", data=tasks_df)
        
        return tasks_df[tasks_df['user_id'] == user_id].copy()
    except:
        return pd.DataFrame(columns=["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"])

def initialize_database():
    """Initialize Google Sheets with required worksheets and columns"""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Define required columns for each worksheet
        users_columns = ["user_id", "username", "password", "name", "email", "created_date"]
        tasks_columns = ["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"]
        
        # Initialize Users worksheet
        try:
            users_df = conn.read(worksheet="Users", ttl=0)
            if users_df.empty:
                users_df = pd.DataFrame(columns=users_columns)
                conn.update(worksheet="Users", data=users_df)
            else:
                # Ensure all columns exist
                for col in users_columns:
                    if col not in users_df.columns:
                        users_df[col] = ""
                conn.update(worksheet="Users", data=users_df)
        except WorksheetNotFound:
            users_df = pd.DataFrame(columns=users_columns)
            conn.create_worksheet(title="Users", data=users_df)
        except Exception as e:
            st.warning(f"Users worksheet initialization: {str(e)}")
            users_df = pd.DataFrame(columns=users_columns)
        
        # Initialize Tasks worksheet
        try:
            tasks_df = conn.read(worksheet="Tasks", ttl=0)
            if tasks_df.empty:
                tasks_df = pd.DataFrame(columns=tasks_columns)
                conn.update(worksheet="Tasks", data=tasks_df)
            else:
                # Ensure all columns exist
                for col in tasks_columns:
                    if col not in tasks_df.columns:
                        tasks_df[col] = ""
                conn.update(worksheet="Tasks", data=tasks_df)
        except WorksheetNotFound:
            tasks_df = pd.DataFrame(columns=tasks_columns)
            conn.create_worksheet(title="Tasks", data=tasks_df)
        except Exception as e:
            st.warning(f"Tasks worksheet initialization: {str(e)}")
            tasks_df = pd.DataFrame(columns=tasks_columns)
        
        # Fill NaN values
        users_df = users_df.fillna("")
        tasks_df = tasks_df.fillna("")
        
        st.session_state.db_initialized = True
        st.session_state.users_df = users_df
        st.session_state.tasks_df = tasks_df
        st.session_state.conn = conn
        return conn, users_df, tasks_df
        
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        return None, pd.DataFrame(), pd.DataFrame()

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
    "Start where you are. Use what you have. Do what you can.",
    "Productivity is never an accident. It is always the result of commitment.",
    "The key is not to prioritize what's on your schedule, but to schedule your priorities."
]
daily_quote = random.choice(QUOTES)

# --- DATABASE INITIALIZATION ---
conn, users_df, tasks_df = initialize_database()

# Store in session state
if conn is not None:
    st.session_state.conn = conn
    st.session_state.users_df = users_df
    st.session_state.tasks_df = tasks_df

# --- LOGIN PAGE ---
if not st.session_state.authenticated:
    st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .login-container {{
            max-width: 450px;
            margin: 50px auto;
            padding: 40px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        .login-header {{
            text-align: center;
            color: {THEME_COLOR};
            margin-bottom: 30px;
            font-size: 2em;
        }}
        .stButton > button {{
            background: {THEME_COLOR};
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: bold;
            transition: all 0.3s;
        }}
        .stButton > button:hover {{
            background: #2980b9;
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(52,152,219,0.4);
        }}
        </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if os.path.exists(ICON_PNG):
                st.image(ICON_PNG, width=120)
            st.markdown("<h1 class='login-header'>RRS Daily Task Manager</h1>", unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])
            
            with tab1:
                with st.form("login_form"):
                    username = st.text_input("Username", placeholder="Enter your username")
                    password = st.text_input("Password", type="password", placeholder="Enter your password")
                    
                    if st.form_submit_button("Login", use_container_width=True):
                        if username and password:
                            user_id, user_name = authenticate_user(username, password, st.session_state.users_df)
                            if user_id:
                                st.session_state.authenticated = True
                                st.session_state.username = username
                                st.session_state.user_id = user_id
                                st.session_state.user_name = user_name
                                st.success("Login successful!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Invalid username or password")
                        else:
                            st.warning("Please enter username and password")
            
            with tab2:
                with st.form("register_form"):
                    new_name = st.text_input("Full Name", placeholder="John Doe")
                    new_email = st.text_input("Email", placeholder="john@example.com")
                    new_username = st.text_input("Username", placeholder="johndoe")
                    new_password = st.text_input("Password", type="password", placeholder="Minimum 6 characters")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    
                    if st.form_submit_button("Register", use_container_width=True):
                        if new_password != confirm_password:
                            st.error("Passwords don't match")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters")
                        elif not new_username or not new_password or not new_name or not new_email:
                            st.error("All fields are required")
                        elif "@" not in new_email or "." not in new_email:
                            st.error("Please enter a valid email address")
                        else:
                            success, result = register_user(new_username, new_password, new_name, new_email, st.session_state.users_df)
                            if success:
                                st.session_state.users_df = result
                                st.session_state.conn.update(worksheet="Users", data=result)
                                st.success("Registration successful! Please login.")
                                st.balloons()
                            else:
                                st.error(result)
    
    st.stop()

# --- MAIN APP (Authenticated) ---
today_str = str(st.session_state.current_date)

# Get user tasks safely
user_tasks_df = get_user_tasks(st.session_state.tasks_df, st.session_state.user_id)

# Ensure all required columns exist
required_task_columns = ["user_id", "task_id", "date", "task", "subnotes", "status", "priority", "due_date", "category", "completed_date"]
for col in required_task_columns:
    if col not in user_tasks_df.columns:
        user_tasks_df[col] = ""

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, {THEME_COLOR}, #2980b9); border-radius: 10px; color: white;">
            <h3>Welcome, {st.session_state.user_name}!</h3>
            <p>{date.today().strftime('%B %d, %Y')}</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Date selector
    st.markdown("#### 📅 View Tasks")
    view_date = st.date_input("Select Date", value=st.session_state.current_date)
    if view_date != st.session_state.current_date:
        st.session_state.current_date = view_date
        st.rerun()
    
    st.divider()
    
    # Categories
    st.markdown("#### 🏷️ Categories")
    categories = ["Work", "Personal", "Urgent", "Follow-up", "Meeting", "Other"]
    selected_category = st.selectbox("Filter by", ["All Tasks"] + categories)
    
    st.divider()
    
    # Quick stats
    st.markdown("#### 📊 Quick Stats")
    pending_count = len(user_tasks_df[user_tasks_df['status'] == 'pending']) if not user_tasks_df.empty else 0
    completed_count = len(user_tasks_df[user_tasks_df['status'] == 'closed']) if not user_tasks_df.empty else 0
    total_count = len(user_tasks_df)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Pending", pending_count)
        st.metric("Completed", completed_count)
    with col2:
        st.metric("Total", total_count)
        completion_rate = (completed_count / total_count * 100) if total_count > 0 else 0
        st.metric("Progress", f"{completion_rate:.1f}%")
    
    st.divider()
    
    # PDF Generation
    st.markdown("#### 📄 Print Tasks")
    if st.button("Generate PDF", use_container_width=True):
        with st.spinner("Generating PDF..."):
            pdf_path = generate_daily_pdf(user_tasks_df, st.session_state.user_name, daily_quote)
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "📥 Download PDF",
                        f,
                        file_name=f"RRS_Tasks_{st.session_state.user_name}_{today_str}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.error("Failed to generate PDF")
    
    st.divider()
    
    # Logout
    if st.button("🚪 Logout", use_container_width=True):
        for key in ['authenticated', 'username', 'user_id', 'user_name', 'current_date']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# --- MAIN CONTENT ---
st.markdown(f"""
    <h1 style='color: {THEME_COLOR}; text-align: center; margin-bottom: 20px;'>
        📋 {st.session_state.user_name}'s Daily Tasks
    </h1>
    <div style='background: linear-gradient(135deg, #EBF5FB, #D4E6F1); padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; font-style: italic; color: #2C3E50; font-size: 1.2em; box-shadow: 0 2px 10px rgba(0,0,0,0.1);'>
        “{daily_quote}”
    </div>
""", unsafe_allow_html=True)

# Get tasks for selected date
if not user_tasks_df.empty:
    if 'due_date' in user_tasks_df.columns:
        if selected_category == "All Tasks":
            today_tasks = user_tasks_df[
                (user_tasks_df['due_date'] <= today_str) | (user_tasks_df['due_date'] == "")
            ]
        else:
            today_tasks = user_tasks_df[
                ((user_tasks_df['due_date'] <= today_str) | (user_tasks_df['due_date'] == "")) &
                (user_tasks_df['category'] == selected_category)
            ]
    else:
        today_tasks = user_tasks_df
else:
    today_tasks = pd.DataFrame()

pending_tasks = today_tasks[today_tasks['status'] == 'pending'].copy() if not today_tasks.empty else pd.DataFrame()
completed_tasks = user_tasks_df[user_tasks_df['status'] == 'closed'].copy() if not user_tasks_df.empty else pd.DataFrame()

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 Today's Tasks", "➕ Add Tasks", "📈 Analytics", "⚙️ Settings"])

with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📌 Pending Tasks ({len(pending_tasks)})")
        
        if not pending_tasks.empty:
            # Sort by priority if column exists
            if 'priority' in pending_tasks.columns:
                priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
                pending_tasks['priority_order'] = pending_tasks['priority'].map(priority_order)
                pending_tasks = pending_tasks.sort_values('priority_order')
            
            for idx, task in pending_tasks.iterrows():
                with st.container():
                    col_a, col_b, col_c = st.columns([0.1, 0.7, 0.2])
                    with col_a:
                        if st.checkbox("", key=f"complete_{idx}"):
                            # Mark as completed
                            if 'task_id' in user_tasks_df.columns and 'task_id' in task:
                                user_tasks_df.loc[user_tasks_df['task_id'] == task['task_id'], 'status'] = 'closed'
                                user_tasks_df.loc[user_tasks_df['task_id'] == task['task_id'], 'completed_date'] = today_str
                            else:
                                # Fallback if no task_id
                                user_tasks_df.loc[idx, 'status'] = 'closed'
                                user_tasks_df.loc[idx, 'completed_date'] = today_str
                            
                            # Update Google Sheet
                            all_tasks = st.session_state.tasks_df[st.session_state.tasks_df['user_id'] != st.session_state.user_id]
                            all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                            st.session_state.conn.update(worksheet="Tasks", data=all_tasks)
                            st.session_state.tasks_df = all_tasks
                            st.rerun()
                    
                    with col_b:
                        st.markdown(f"**{task['task']}**")
                        if task.get('subnotes'):
                            st.caption(f"📝 {task['subnotes']}")
                        if task.get('category'):
                            st.caption(f"🏷️ {task['category']}")
                        if task.get('priority'):
                            priority_colors = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}
                            st.caption(f"{priority_colors.get(task['priority'], '⚪')} {task['priority']}")
                    
                    with col_c:
                        if task.get('due_date') and task['due_date'] and task['due_date'] != today_str:
                            try:
                                due = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
                                days_left = (due - date.today()).days
                                if days_left < 0:
                                    st.markdown(f"<span style='color: #ff4444;'>Overdue!</span>", unsafe_allow_html=True)
                                elif days_left == 0:
                                    st.markdown(f"<span style='color: #ffbb33;'>Today</span>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"{days_left}d left", unsafe_allow_html=True)
                            except:
                                pass
                    
                    st.divider()
        else:
            st.info("🎉 No pending tasks for today! Time to add some new tasks?")
    
    with col2:
        st.subheader("✅ Completed Today")
        if not completed_tasks.empty and 'completed_date' in completed_tasks.columns:
            today_completed = completed_tasks[completed_tasks['completed_date'] == today_str]
            if not today_completed.empty:
                for _, task in today_completed.iterrows():
                    st.markdown(f"~~{task['task']}~~")
                    if task.get('category'):
                        st.caption(f"🏷️ {task['category']}")
            else:
                st.info("No tasks completed today yet.")
        else:
            st.info("No tasks completed today yet.")
        
        st.divider()
        
        # Upcoming tasks
        st.subheader("📅 Upcoming")
        if not user_tasks_df.empty and 'due_date' in user_tasks_df.columns and 'status' in user_tasks_df.columns:
            upcoming = user_tasks_df[
                (user_tasks_df['due_date'] > today_str) & 
                (user_tasks_df['status'] == 'pending')
            ].sort_values('due_date').head(5)
            
            if not upcoming.empty:
                for _, task in upcoming.iterrows():
                    try:
                        due = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
                        days_left = (due - date.today()).days
                        st.markdown(f"• {task['task']} ({days_left}d)")
                    except:
                        st.markdown(f"• {task['task']}")
            else:
                st.info("No upcoming tasks")

with tab2:
    st.subheader("➕ Add New Tasks")
    
    with st.form("add_task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_task = st.text_input("Task Title *", placeholder="e.g., Follow up on BCT Loan")
            new_category = st.selectbox("Category", categories, index=0)
            new_priority = st.select_slider("Priority", options=["Low", "Medium", "High"], value="Medium")
        
        with col2:
            new_due_date = st.date_input("Due Date", value=date.today())
            repeat_option = st.selectbox("Repeat", ["None", "Daily", "Weekly", "Monthly"])
            if repeat_option != "None":
                repeat_until = st.date_input("Repeat Until", value=date.today() + timedelta(days=30))
        
        new_subnotes = st.text_area("Additional Notes", height=100, placeholder="Add any details, links, or notes...")
        
        submitted = st.form_submit_button("📥 Add Task", use_container_width=True)
        
        if submitted:
            if new_task.strip():
                task_id = hashlib.md5(f"{new_task}{datetime.now()}{random.random()}".encode()).hexdigest()[:12]
                
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
                
                if user_tasks_df.empty:
                    user_tasks_df = new_row
                else:
                    user_tasks_df = pd.concat([user_tasks_df, new_row], ignore_index=True)
                
                # Handle repeating tasks
                if repeat_option != "None":
                    current_date = new_due_date
                    while current_date <= repeat_until:
                        current_date += timedelta(days=1 if repeat_option == "Daily" else 7 if repeat_option == "Weekly" else 30)
                        if current_date <= repeat_until:
                            future_task_id = hashlib.md5(f"{new_task}{current_date}{random.random()}".encode()).hexdigest()[:12]
                            future_row = pd.DataFrame([{
                                'user_id': st.session_state.user_id,
                                'task_id': future_task_id,
                                'date': str(current_date),
                                'task': new_task.strip(),
                                'subnotes': new_subnotes.strip(),
                                'status': 'pending',
                                'priority': new_priority,
                                'due_date': str(current_date),
                                'category': new_category,
                                'completed_date': ""
                            }])
                            user_tasks_df = pd.concat([user_tasks_df, future_row], ignore_index=True)
                
                # Update Google Sheet
                all_tasks = st.session_state.tasks_df[st.session_state.tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                st.session_state.conn.update(worksheet="Tasks", data=all_tasks)
                st.session_state.tasks_df = all_tasks
                
                st.success("✅ Task added successfully!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            else:
                st.error("Task title is required!")

with tab3:
    st.subheader("📊 Task Analytics")
    
    if not user_tasks_df.empty and 'completed_date' in user_tasks_df.columns:
        # Task completion trend
        st.markdown("#### 📈 Completion Trend (Last 7 Days)")
        last_7_days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        
        completion_data = []
        for day in last_7_days:
            day_completed = len(user_tasks_df[
                (user_tasks_df['completed_date'] == day) & 
                (user_tasks_df['status'] == 'closed')
            ])
            completion_data.append(day_completed)
        
        chart_data = pd.DataFrame({
            'Date': [d[-5:] for d in last_7_days],
            'Completed': completion_data
        })
        
        st.bar_chart(chart_data.set_index('Date'))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Category distribution
            st.markdown("#### 📊 Tasks by Category")
            if 'category' in user_tasks_df.columns and 'status' in user_tasks_df.columns:
                category_counts = user_tasks_df[user_tasks_df['status'] == 'pending']['category'].value_counts()
                if not category_counts.empty:
                    st.bar_chart(category_counts)
                else:
                    st.info("No data available")
        
        with col2:
            # Priority breakdown
            st.markdown("#### 🎯 Priority Breakdown")
            if 'priority' in user_tasks_df.columns and 'status' in user_tasks_df.columns:
                priority_counts = user_tasks_df[user_tasks_df['status'] == 'pending']['priority'].value_counts()
                if not priority_counts.empty:
                    fig_data = pd.DataFrame({
                        'Priority': priority_counts.index,
                        'Count': priority_counts.values
                    }).set_index('Priority')
                    st.bar_chart(fig_data)
                else:
                    st.info("No data available")
        
        # Productivity insights
        st.markdown("#### 💡 Productivity Insights")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            days_active = 1
            if not st.session_state.users_df.empty and 'created_date' in st.session_state.users_df.columns:
                user_data = st.session_state.users_df[st.session_state.users_df['user_id'] == st.session_state.user_id]
                if not user_data.empty and user_data.iloc[0]['created_date']:
                    try:
                        created = datetime.strptime(user_data.iloc[0]['created_date'], '%Y-%m-%d').date()
                        days_active = max(1, (date.today() - created).days)
                    except:
                        pass
            avg_completed_per_day = len(user_tasks_df[user_tasks_df['status'] == 'closed']) / days_active
            st.metric("Avg Tasks/Day", f"{avg_completed_per_day:.1f}")
        
        with col2:
            if 'completed_date' in user_tasks_df.columns and not user_tasks_df[user_tasks_df['completed_date'] != ""].empty:
                most_productive_day = user_tasks_df[user_tasks_df['completed_date'] != ""]['completed_date'].value_counts().index[0]
                st.metric("Best Day", most_productive_day[-5:] if most_productive_day else "N/A")
            else:
                st.metric("Best Day", "N/A")
        
        with col3:
            completion_streak = calculate_streak(user_tasks_df)
            st.metric("Current Streak", f"{completion_streak} days")
    else:
        st.info("No data available for analytics yet. Start adding tasks to see insights!")

with tab4:
    st.subheader("⚙️ Settings")
    
    # Get user email safely
    user_email = ""
    if not st.session_state.users_df.empty and 'email' in st.session_state.users_df.columns:
        user_data = st.session_state.users_df[st.session_state.users_df['user_id'] == st.session_state.user_id]
        if not user_data.empty:
            user_email = user_data.iloc[0]['email']
    
    with st.form("settings_form"):
        st.markdown("#### 📧 Email Preferences")
        new_email = st.text_input("Email Address for Daily PDF", value=user_email)
        
        st.markdown("#### 🎨 Display Preferences")
        theme = st.selectbox("Theme", ["Light", "Dark", "System Default"])
        show_completed = st.checkbox("Show completed tasks in main view", value=False)
        
        st.markdown("#### 🔔 Notifications")
        email_daily = st.checkbox("Receive daily PDF via email", value=True)
        email_time = st.time_input("Daily PDF Time", value=datetime.strptime("08:00", "%H:%M").time())
        
        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            # Update user email if changed
            if new_email != user_email and not st.session_state.users_df.empty:
                st.session_state.users_df.loc[st.session_state.users_df['user_id'] == st.session_state.user_id, 'email'] = new_email
                st.session_state.conn.update(worksheet="Users", data=st.session_state.users_df)
            st.success("Settings saved successfully!")
    
    st.divider()
    
    st.markdown("#### 🗑️ Data Management")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Export My Data", use_container_width=True):
            csv = user_tasks_df.to_csv(index=False)
            st.download_button(
                "📥 Download CSV",
                csv,
                file_name=f"my_tasks_{today_str}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("Delete Completed Tasks", use_container_width=True, type="secondary"):
            confirm = st.checkbox("Confirm deletion of all completed tasks")
            if confirm and not user_tasks_df.empty:
                user_tasks_df = user_tasks_df[user_tasks_df['status'] != 'closed']
                all_tasks = st.session_state.tasks_df[st.session_state.tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                st.session_state.conn.update(worksheet="Tasks", data=all_tasks)
                st.session_state.tasks_df = all_tasks
                st.success("Completed tasks deleted!")
                st.rerun()

# --- EVENING SYNC ---
st.divider()
st.markdown(f"""
    <h2 style='color: {THEME_COLOR}; text-align: center;'>🌙 Evening Sync</h2>
    <p style='text-align: center;'>Upload your completed task sheet to sync completed tasks and add new ones</p>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload scanned/photo of your completed task sheet", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    image = Image.open(uploaded_file)
    img_array = np.array(image)
    st.image(image, caption="Uploaded Sheet", width=400)
    
    @st.cache_resource
    def load_reader():
        return easyocr.Reader(['en'])
    
    with st.spinner("Analyzing your sheet..."):
        reader = load_reader()
        results = reader.readtext(img_array, paragraph=False)
        
        # Extract text
        found_text = []
        template_words = ["rrs", "daily", "task", "date", "priorities", "incoming", "notes", "today", "grateful"]
        
        for (bbox, text, prob) in results:
            if prob > 0.3 and len(text.strip()) > 2:
                clean_text = re.sub(r'[^\w\s]', '', text).strip()
                is_template = any(word in clean_text.lower() for word in template_words)
                if not is_template and not clean_text.replace(" ", "").isdigit():
                    found_text.append(clean_text)
        
        # Separate completed and new tasks
        completed_tasks = []
        new_tasks = []
        
        for text in found_text:
            if any(mark in text.lower() for mark in ["x", "done", "completed", "✓", "✅", "✔"]):
                clean_text = re.sub(r'[x✓✅✔]', '', text, flags=re.IGNORECASE).strip()
                completed_tasks.append(clean_text)
            else:
                new_tasks.append(text)
    
    with st.form("evening_sync_form"):
        st.markdown("### 📋 Review Detected Items")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### ✅ Completed Tasks")
            if completed_tasks:
                selected_completed = []
                for i, task in enumerate(completed_tasks[:10]):
                    if st.checkbox(task, key=f"comp_{i}"):
                        selected_completed.append(task)
            else:
                st.info("No completed tasks detected")
        
        with col2:
            st.markdown("#### 📝 New Tasks to Add")
            if new_tasks:
                new_task_inputs = []
                for i, task in enumerate(new_tasks[:10]):
                    with st.expander(f"Task {i+1}"):
                        edited_task = st.text_input("Task", value=task, key=f"new_task_{i}")
                        task_due = st.date_input("Due Date", value=date.today(), key=f"due_{i}")
                        task_category = st.selectbox("Category", categories, key=f"cat_{i}")
                        task_priority = st.select_slider("Priority", options=["Low", "Medium", "High"], value="Medium", key=f"pri_{i}")
                        add_task = st.checkbox("Add this task", value=True, key=f"add_{i}")
                        
                        if add_task:
                            new_task_inputs.append({
                                'task': edited_task,
                                'due_date': str(task_due),
                                'category': task_category,
                                'priority': task_priority
                            })
            else:
                st.info("No new tasks detected")
        
        st.divider()
        
        sync_submit = st.form_submit_button("🚀 Process Evening Sync", use_container_width=True)
        
        if sync_submit:
            changes_made = False
            
            # Mark completed tasks
            if 'selected_completed' in locals() and selected_completed:
                for task_text in selected_completed:
                    for idx, task in user_tasks_df[user_tasks_df['status'] == 'pending'].iterrows():
                        if task_text.lower() in task['task'].lower() or task['task'].lower() in task_text.lower():
                            user_tasks_df.loc[idx, 'status'] = 'closed'
                            user_tasks_df.loc[idx, 'completed_date'] = today_str
                            changes_made = True
                            break
            
            # Add new tasks
            if 'new_task_inputs' in locals() and new_task_inputs:
                for task_data in new_task_inputs:
                    task_id = hashlib.md5(f"{task_data['task']}{datetime.now()}{random.random()}".encode()).hexdigest()[:12]
                    new_row = pd.DataFrame([{
                        'user_id': st.session_state.user_id,
                        'task_id': task_id,
                        'date': today_str,
                        'task': task_data['task'],
                        'subnotes': "",
                        'status': 'pending',
                        'priority': task_data['priority'],
                        'due_date': task_data['due_date'],
                        'category': task_data['category'],
                        'completed_date': ""
                    }])
                    
                    if user_tasks_df.empty:
                        user_tasks_df = new_row
                    else:
                        user_tasks_df = pd.concat([user_tasks_df, new_row], ignore_index=True)
                    changes_made = True
            
            if changes_made:
                # Update Google Sheet
                all_tasks = st.session_state.tasks_df[st.session_state.tasks_df['user_id'] != st.session_state.user_id]
                all_tasks = pd.concat([all_tasks, user_tasks_df], ignore_index=True)
                st.session_state.conn.update(worksheet="Tasks", data=all_tasks)
                st.session_state.tasks_df = all_tasks
                st.success("✅ Evening sync completed successfully!")
                st.balloons()
                time.sleep(2)
                st.rerun()
            else:
                st.warning("No changes detected")