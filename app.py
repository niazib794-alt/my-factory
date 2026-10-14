import streamlit as st
import google.generativeai as genai
import urllib.parse

# پیج کی سیٹنگ
st.set_page_config(page_title="خودکار بزنس فیکٹری", layout="wide")
st.title("🏭 خودکار بزنس فیکٹری (Multi-AI Engine)")

# ----------------- سائیڈ بار (API Keys کی سیٹنگ) -----------------
st.sidebar.header("🔑 API Keys سیٹنگز")
st.sidebar.write("اپنی دستیاب API Keys نیچے درج کریں:")

# 1. Google Gemini API Keys (3 مختلف کیز کی گنجائش)
gemini_key_1 = st.sidebar.text_input("Gemini API Key 1", type="password")
gemini_key_2 = st.sidebar.text_input("Gemini API Key 2 (Secondary)", type="password")
gemini_key_3 = st.sidebar.text_input("Gemini API Key 3 (Backup)", type="password")

# 2. دیگر AI سروسز کی Keys
openrouter_key = st.sidebar.text_input("OpenRouter API Key", type="password")
perplexity_key = st.sidebar.text_input("Perplexity API Key", type="password")
openai_key     = st.sidebar.text_input("OpenAI / Microsoft API Key", type="password")
pollinations_key = st.sidebar.text_input("Pollinations Key (Optional)", type="password")

# فعال (Active) Gemini Key کا انتخاب
active_gemini_key = gemini_key_1 or gemini_key_2 or gemini_key_3

# ----------------- مین ایپ (Main Application) -----------------
prompt = st.text_input("اپنا بزنس آئیڈیا یا موضوع لکھیں:")

if st.button("بزنس پلان اور ڈیزائن تیار کریں"):
    if not active_gemini_key:
        st.error("براہ کرم سائیڈ بار میں کم از کم ایک Gemini API Key درج کر کے Enter دبائیں!")
    else:
        with st.spinner("AI دماغ کام کر رہے ہیں..."):
            try:
                # Gemini API کانفیگر کریں
                genai.configure(api_key=active_gemini_key)
                
                # Gemini Pro ماڈل استعمال کریں (Found error سے بچنے کے لیے)
                model = genai.GenerativeModel('gemini-pro')
                
                # متن تیار کرنا (Text Generation)
                response = model.generate_content(f"Create a detailed business plan for: {prompt}")
                st.subheader("📊 مارکیٹ تجزیہ و پلان")
                st.write(response.text)

                # تصویر تیار کرنا (Pollinations AI)
                image_prompt = urllib.parse.quote(f"Professional business design for: {prompt}")
                image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
                st.image(image_url, caption="خودکار ڈیزائن (Pollinations AI)")

            except Exception as e:
                st.error(f"ایرر آ گیا ہے: {e}")
                st.info("اگر پہلی Key کام نہیں کر رہی تو سائیڈ بار میں دوسری Gemini Key ڈال کر کوشش کریں۔")
