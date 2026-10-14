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
        with st.spinner("8 AI دماغ کام کر رہے ہیں..."):
            # Brain Analysis
            response = model.generate_content(f"Create a complete business plan for: {prompt}")
            st.subheader("📊 مارکیٹ تجزیہ و پلان")
            st.write(response.text)

            # Image Generator Link
            image_prompt = urllib.parse.quote(f"Professional marketing poster for {prompt}")
            image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
            st.image(image_url, caption="خودکار ڈیزائن")

            # PDF Generation
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Business Factory Report", ln=1, align='C')
            pdf.multi_cell(0, 10, response.text.encode('latin-1', 'replace').decode('latin-1'))
            pdf_output = pdf.output(dest='S').encode('latin-1')

            st.download_button(label="📄 PDF ڈاؤنلوڈ کریں", data=pdf_output, file_name="business_plan.pdf", mime="application/pdf")
else:
    st.warning("براہ کرم ایپ چلانے کے لیے سائیڈ بار میں اپنی Gemini API Key درج کریں۔")
