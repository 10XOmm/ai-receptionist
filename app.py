import os
import io
import csv
from datetime import date
import streamlit as st
from agent import (
    ingest_pdf,
    get_indexed_files,
    clear_database,
    get_leads,
    validate_contact,
    save_customer_lead,
    generate_response,
)

# --- EASY CLIENT REBRANDING & GUARDRAILS ---
BUSINESS_NAME = "Al-Noor Dental & Aesthetic Clinic"
BUSINESS_SUBTITLE = "24/7 AI Assistant — Ask about our services, prices, hours, or book an appointment (English / العربية)."

try:
    ADMIN_PIN = str(st.secrets.get("ADMIN_PIN", os.getenv("ADMIN_PIN", "1234"))).strip()
except Exception:
    ADMIN_PIN = os.getenv("ADMIN_PIN", "1234").strip()

# Closed weekdays: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
CLOSED_WEEKDAYS = [4]  # Friday closed
VALID_TIME_SLOTS = [
    "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM",
    "12:00 PM", "12:30 PM", "01:00 PM", "01:30 PM", "02:00 PM", "02:30 PM",
    "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM", "05:00 PM", "05:30 PM",
    "06:00 PM", "06:30 PM", "07:00 PM", "07:30 PM", "08:00 PM", "08:30 PM",
]

st.set_page_config(
    page_title=f"{BUSINESS_NAME} | AI Assistant",
    page_icon="💬",
    layout="wide",
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False
if "trigger_booking" not in st.session_state:
    st.session_state.trigger_booking = False


def leads_to_csv_bytes(leads: list[dict]) -> bytes:
    if not leads:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=leads[0].keys())
    writer.writeheader()
    writer.writerows(leads)
    return output.getvalue().encode("utf-8")


# --- GUI BOOKING POPUP WITH CODE-LEVEL GUARDRAILS ---
@st.dialog("📅 Book an Appointment")
def booking_modal():
    st.caption("Fill in your details below. Working hours: 9:00 AM – 9:00 PM (Closed Fridays).")

    name = st.text_input("Full Name *", placeholder="e.g., Omar Fourani")
    contact = st.text_input("WhatsApp / Phone Number or Email *", placeholder="e.g., +971 50 123 4567")
    service = st.text_input("Service / Reason for Visit *", placeholder="e.g., Dental Consultation, Whitening")

    col_d, col_t = st.columns(2)
    with col_d:
        appt_date = st.date_input("Preferred Date *", min_value=date.today())
    with col_t:
        appt_time = st.selectbox("Preferred Time *", VALID_TIME_SLOTS)

    if st.button("✅ Confirm Booking", type="primary", use_container_width=True):
        errors = []
        if not name.strip() or len(name.strip()) < 2:
            errors.append("Please enter your full name.")
        if not validate_contact(contact):
            errors.append("Please enter a valid phone/WhatsApp number (digits only, no letters) or a valid email.")
        if not service.strip():
            errors.append("Please enter the service you'd like to book.")
        if appt_date.weekday() in CLOSED_WEEKDAYS:
            errors.append("We are closed on Fridays. Please choose another day.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            preferred_slot = f"{appt_date.strftime('%Y-%m-%d')} at {appt_time}"
            save_customer_lead(name, contact, service, preferred_slot)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        f"✅ **Booking Confirmed!**\n\n"
                        f"- **Name:** {name.strip()}\n"
                        f"- **Contact:** {contact.strip()}\n"
                        f"- **Service:** {service.strip()}\n"
                        f"- **Time:** {preferred_slot}\n\n"
                        f"Our team will reach out shortly to confirm your visit."
                    ),
                }
            )
            st.rerun()


# --- SIDEBAR (ADMIN PORTAL) ---
with st.sidebar:
    st.header("🔒 Staff & Admin Portal")

    if not st.session_state.admin_unlocked:
        pin_input = st.text_input("Enter Admin PIN", type="password", placeholder="••••")
        if st.button("Unlock Admin Panel", use_container_width=True):
            if pin_input == ADMIN_PIN:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect PIN.")
        st.caption("Customers can ignore this panel and chat directly on the right.")
    else:
        if st.button("🔓 Lock Admin Panel", use_container_width=True):
            st.session_state.admin_unlocked = False
            st.rerun()

        st.divider()
        st.subheader("📁 Company Knowledge Base")
        uploaded_files = st.file_uploader(
            "Upload Company PDFs (Pricing, Policies, FAQs)",
            type=["pdf"],
            accept_multiple_files=True,
        )

        if st.button("Process & Index PDFs", type="primary", use_container_width=True):
            if uploaded_files:
                total_chunks = 0
                with st.spinner("Indexing documents..."):
                    for file in uploaded_files:
                        total_chunks += ingest_pdf(file.read(), file.name)
                st.success(f"Indexed {len(uploaded_files)} file(s) ({total_chunks} chunks).")
                st.rerun()
            else:
                st.warning("Upload at least one PDF first.")

        st.subheader("Active Documents")
        indexed_files = get_indexed_files()
        if indexed_files:
            for fname in indexed_files:
                st.markdown(f"- 📄 `{fname}`")
            if st.button("Clear Database", use_container_width=True):
                clear_database()
                st.success("Knowledge base cleared.")
                st.rerun()
        else:
            st.caption("No documents indexed yet.")

        st.divider()
        st.subheader("🎯 Captured Customer Leads")
        leads = get_leads()
        if leads:
            st.dataframe(leads, use_container_width=True, hide_index=True)
            st.download_button(
                label="⬇️ Download Leads (CSV)",
                data=leads_to_csv_bytes(leads),
                file_name="captured_leads.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No leads captured yet.")


# --- MAIN CUSTOMER CHAT INTERFACE ---
col1, col2, col3 = st.columns([4, 1.3, 1])
with col1:
    st.title(f"💬 {BUSINESS_NAME}")
    st.caption(BUSINESS_SUBTITLE)
with col2:
    if st.button("📅 Book Appointment", type="primary", use_container_width=True):
        st.session_state.trigger_booking = True
with col3:
    if st.button("🔄 New Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.divider()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask a question in English or Arabic..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                reply = generate_response(prompt, st.session_state.messages[:-1])
                if "[OPEN_BOOKING]" in reply:
                    clean_reply = reply.replace("[OPEN_BOOKING]", "").strip()
                    st.session_state.messages.append({"role": "assistant", "content": clean_reply})
                    st.session_state.trigger_booking = True
                    st.rerun()
                else:
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"⚠️ Error communicating with AI: {e}")

# Open the booking popup if triggered by chat or button
if st.session_state.trigger_booking:
    st.session_state.trigger_booking = False
    booking_modal()
