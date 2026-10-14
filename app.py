import streamlit as st
import google.generativeai as genai
import urllib.parse

st.set_page_config(page_title="خودکار بزنس فیکٹری", layout="wide")
st.title("🏭 خودکار بزنس فیکٹری (Multi-AI Engine)")

st.sidebar.header("🔑 API Keys سیٹنگز")
gemini_key_1 = st.sidebar.text_input("Gemini API Key 1", type="password")
gemini_key_2 = st.sidebar.text_input("Gemini API Key 2 (Secondary)", type="password")
gemini_key_3 = st.sidebar.text_input("Gemini API Key 3 (Backup)", type="password")

openrouter_key = st.sidebar.text_input("OpenRouter API Key", type="password")
perplexity_key = st.sidebar.text_input("Perplexity API Key", type="password")
openai_key     = st.sidebar.text_input("OpenAI / Microsoft API Key", type="password")
pollinations_key = st.sidebar.text_input("Pollinations Key (Optional)", type="password")

active_gemini_key = gemini_key_1 or gemini_key_2 or gemini_key_3

prompt = st.text_input("اپنا بزنس آئیڈیا یا موضوع لکھیں:")

if st.button("بزنس پلان اور ڈیزائن تیار کریں"):
    if not active_gemini_key:
        st.error("براہ کرم سائیڈ بار میں کم از کم ایک Gemini API Key درج کر کے Enter دبائیں!")
    else:
        with st.spinner("ماڈلز چیک کیے جا رہے ہیں..."):
            try:
                genai.configure(api_key=active_gemini_key)
                
                # دستیاب ماڈلز کی فہرست
                models_to_try = [
                    'gemini-1.5-flash',
                    'gemini-1.5-pro',
                    'gemini-pro'
                ]
                
                response = None
                success_model = None
                last_error = ""
                
                for m_name in models_to_try:
                    try:
                        model = genai.GenerativeModel(m_name)
                        response = model.generate_content(f"Create a detailed business plan for: {prompt}")
                        if response and response.text:
                            success_model = m_name
                            break
                    except Exception as err:
                        last_error = str(err)
                        continue
                
                if response and response.text:
                    st.success(f"کامیاب ماڈل: {success_model}")
                    st.subheader("📊 مارکیٹ تجزیہ و پلان")
                    st.write(response.text)

                    image_prompt = urllib.parse.quote(f"Professional business design for: {prompt}")
                    image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
                    st.image(image_url, caption="خودکار ڈیزائن (Pollinations AI)")
                else:
                    st.error(f"ایرر تفصیل: {last_error}")
                    st.info("گوگل اے آئی اسٹوڈیو سے بالکل نیا پروجیکٹ بنا کر نئی API Key حاصل کریں۔")

            except Exception as e:
                st.error(f"تکنیکی خرابی: {e}")
