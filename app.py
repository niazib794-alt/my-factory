import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import urllib.parse

st.set_page_config(page_title="خودکار بزنس فیکٹری", layout="wide")

st.title("🏭 خودکار بزنس فیکٹری (8 AI برینز)")

api_key = st.sidebar.text_input("اپنی Gemini API Key درج کریں")

if api_key:
    genai.configure(api_key=api_key)

model = genai.GenerativeModel('gemini-1.5-flash')

prompt = st.text_input("اپنا بزنس آئیڈیا یا موضوع لکھیں")

if st.button("بزنس پلان اور ڈیزائن تیار کریں"):
    if not api_key:
        st.error("براہ کرم پہلے سائیڈ بار میں اپنی Gemini API Key درج کریں!")
    else:
        with st.spinner("8 AI دماغ کام کر رہے ہیں..."):
            # Brain Analysis
            response = model.generate_content(f"Create a complete plan for: {prompt}")
            st.subheader("📊 مارکیٹ تجزیہ و پلان")
            st.write(response.text)

            # Image Generator Link
            image_prompt = urllib.parse.quote(f"Professional design for: {prompt}")
            image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
            st.image(image_url, caption="خودکار ڈیزائن")
