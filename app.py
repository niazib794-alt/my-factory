import streamlit as st
import google.generativeai as genai
import urllib.parse

# پیج کی سیٹنگ
st.set_page_config(page_title="خودکار بزنس فیکٹری", layout="wide")
st.title("🏭 خودکار بزنس فیکٹری (Multi-AI Engine)")

# ----------------- سائیڈ بار (API Keys کی سیٹنگ) -----------------
st.sidebar.header("🔑 API Keys سیٹنگز")
st.sidebar.write("اپنی دستیاب API Keys نیچے درج کریں:")

# 1. Google Gemini API Keys (متعدد کیز کی گنجائش)
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
        with st.spinner("AI ماڈلز کوشش کر رہے ہیں..."):
            try:
                # Gemini API کانفیگر کریں
                genai.configure(api_key=active_gemini_key)
                
                # ماڈلز کی فہرست جن کو ایک کے بعد ایک ٹیسٹ کیا جائے گا
                models_to_try = [
                    'gemini-1.5-flash',
                    'gemini-1.5-flash-latest',
                    'gemini-1.5-pro',
                    'gemini-1.5-pro-latest',
                    'gemini-pro'
                ]
                
                response = None
                success_model = None
                
                # ایک ایک کر کے ماڈل چیک کریں گے جب تک کوئی ایک کام نہ کر جائے
                for m_name in models_to_try:
                    try:
                        model = genai.GenerativeModel(m_name)
                        response = model.generate_content(f"Create a detailed business plan for: {prompt}")
                        if response and response.text:
                            success_model = m_name
                            break
                    except Exception:
                        continue # اگر یہ نہیں چلا تو اگلے ماڈل پر چلے جاؤ
                
                if response and response.text:
                    st.success(s_msg := f"کامیاب ماڈل: {success_model}")
                    st.subheader("📊 مارکیٹ تجزیہ و پلان")
                    st.write(response.text)

                    # تصویر تیار کرنا (Pollinations AI)
                    image_prompt = urllib.parse.quote(f"Professional business design for: {prompt}")
                    image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
                    st.image(image_url, caption="خودکار ڈیزائن (Pollinations AI)")
                else:
                    st.error("کوئی بھی دستیاب ماڈل اس کی پر رسپانس نہیں دے سکا۔ براہ کرم اپنی API Key چیک کریں۔")

            except Exception as e:
                st.error(f"تکنیکی خرابی: {e}")
                st.info("براہ کرم یقینی بنائیں کہ آپ نے سائیڈ بار میں درست Gemini API Key دی ہے۔")
