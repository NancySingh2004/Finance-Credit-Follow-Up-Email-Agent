#from apscheduler.schedulers.background import BackgroundScheduler # type: ignore
#import time
import smtplib
from email.mime.text import MIMEText
import pandas as pd
from datetime import datetime
from langchain_groq import ChatGroq # type: ignore
from langchain_core.prompts import PromptTemplate # type: ignore
from langchain_core.output_parsers import StrOutputParser # type: ignore
from dotenv import load_dotenv
import os
import streamlit as st

# ENV SETUP
load_dotenv()
DRY_RUN = True

llm = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name="llama-3.1-8b-instant"
)

def send_email(receiver_email, subject, body):

    if DRY_RUN:
        print("\n====== DRY RUN EMAIL ======")
        print("TO:", receiver_email)
        print("SUBJECT:", subject)
        print(body)
        print("====== EMAIL NOT SENT ======\n")
        return "Dry Run Success"

    sender_email = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, app_password)
    server.send_message(msg)
    server.quit()

    return "Email Sent"


# LOAD DATA
df = pd.read_csv("invoices.csv")
df["due_date"] = pd.to_datetime(df["due_date"])

today = datetime.today()
df["days_overdue"] = (today - df["due_date"]).dt.days

audit_logs = []
if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = []
# Session state for storing generated emails
if "emails" not in st.session_state:
    st.session_state.emails = {}


# FOLLOW-UP TONE LOGIC
def get_followup_tone(days):

    if 1 <= days <= 7:
        return "Warm & Friendly"

    elif 8 <= days <= 14:
        return "Polite but Firm"

    elif 15 <= days <= 21:
        return "Formal & Serious"

    elif 22 <= days <= 30:
        return "Stern & Urgent"

    else:
        return "Legal Escalation"


# LANGCHAIN EMAIL GENERATION
def generate_email(row, stage):

    template = """
You are a professional finance assistant.

Write a clear and professional payment reminder email.

STRICT RULES:
- No placeholders
- No extra explanations
- Tone must match: {stage}
- Output ONLY the email

COMPANY DETAILS:
Finance Team XYZ
Email: finance@xyz.com
Phone: +91-9999999999

CLIENT DETAILS:
Name: {client_name}
Email: {email}
Invoice: {invoice_no}
Amount: ₹{amount}
Due Date: {due_date}
Follow-up Count: {follow_up_count}
Days Overdue: {days_overdue}
"""

    prompt = PromptTemplate(
        input_variables=[
            "stage",
            "client_name",
            "email",
            "invoice_no",
            "amount",
            "due_date",
            "follow_up_count",
            "days_overdue"
        ],
        template=template
    )

    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "stage": stage,
        "client_name": row["client_name"],
        "email": row["email"],
        "invoice_no": row["invoice_no"],
        "amount": row["amount"],
        "due_date": row["due_date"].date(),
        "follow_up_count": row["follow_up_count"],
        "days_overdue": row["days_overdue"]
    })

    return response


# STREAMLIT UI CONFIG
st.set_page_config(page_title="Finance Email Agent", layout="wide", page_icon="")

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("System Control Panel")
    st.markdown("---")
    
    # Status Indicators
    st.info(f"**Mode:** {'Dry Run Active' if DRY_RUN else ' Live Mode'}")
    st.write(f"Total Invoices Loaded: `{len(df)}`")
    
    st.markdown("---")
    st.subheader("Data Export")
    if st.button(" Save Audit Log", use_container_width=True):
        if st.session_state.audit_logs:
            pd.DataFrame(st.session_state.audit_logs).to_csv("audit_log.csv", index=False)
            st.success("Audit log saved successfully!")
        else:
            st.warning("No action items logged in this session yet.")

# --- MAIN PAGE ---
st.title(" AI Finance Email Agent")
st.caption("Automate and manage your intelligent invoice collections with customized tone escalations.")
st.markdown("---")

# -------------------------
# DISPLAY DATA
# -------------------------
for i, row in df.iterrows():
    stage = get_followup_tone(row["days_overdue"])
    
    # Render each row inside a modern styled Card Container
    with st.container(border=True):
        
        # Header Row inside Card
        head_col1, head_col2 = st.columns([3, 1])
        with head_col1:
            st.subheader(f" {row['client_name']}")
        with head_col2:
            # Color badge depending on tone severity
            if "Warm" in stage:
                st.success(f" {stage}")
            elif "Polite" in stage or "Formal" in stage:
                st.warning(f" {stage}")
            else:
                st.error(f" {stage}")

        # Metrics Row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Invoice Number", row["invoice_no"])
        col2.metric("Amount Due", f"₹{row['amount']:,}")
        col3.metric("Days Overdue", f"{row['days_overdue']} Days")
        col4.metric("Follow-up count", row["follow_up_count"])

        # ESCALATION LOGIC
        if row["days_overdue"] >= 30:
            st.error(" **Manual Finance Review Required:** This invoice has breached the 30-day window. Manual legal tracking requested.")
            
            # Avoid appending duplicates to the session log blindly on simple rerenders
            if not any(log['invoice_no'] == row['invoice_no'] and log['status'] == 'Escalated' for log in audit_logs):
                st.session_state.audit_logs.append({
                    "timestamp": datetime.now(),
                    "client": row["client_name"],
                    "invoice_no": row["invoice_no"],
                    "stage": stage,
                    "status": "Escalated"
                })
            continue

        # Split Generation actions and Results into Tabs inside the card to keep it clean
        tab1, tab2 = st.tabs([" Actions", " Saved Draft Workspace"])

        with tab1:
            button_key = f"btn_{row['invoice_no']}"
            if st.button(" Draft Collection Email", key=button_key, type="primary"):
                with st.spinner("AI is analyzing records & drafting..."):
                    email = generate_email(row, stage)
                    st.session_state.emails[row["invoice_no"]] = email
                    
                    st.session_state.audit_logs.append({
                        "timestamp": datetime.now(),
                        "client": row["client_name"],
                        "invoice_no": row["invoice_no"],
                        "stage": stage,
                        "status": "Email Generated"
                    })
                st.rerun()

        with tab2:
            # SHOW PREVIOUS EMAIL IF EXISTS
            if row["invoice_no"] in st.session_state.emails:
                st.caption("Review or edit the AI generated response before dispatching:")
                
                # Allow live tweaking directly in the UI text box
                current_email_body = st.text_area(
                    "Email Draft Content",
                    st.session_state.emails[row["invoice_no"]],
                    height=230,
                    key=f"text_{row['invoice_no']}"
                )
                st.session_state.emails[row["invoice_no"]] = current_email_body

                if st.button(f" Dispatch Email", key=f"send_{row['invoice_no']}", use_container_width=True):
                    subject = f"Payment Reminder - {row['invoice_no']}"
                    
                    with st.spinner("Sending email context..."):
                        send_email(
                            receiver_email=row["email"],
                            subject=subject,
                            body=current_email_body
                        )
                    st.success(f" Run verification successful for {row['client_name']}!")
            else:
                st.info("No draft prepared yet. Go to the Actions tab to create an automated communication strategy.")