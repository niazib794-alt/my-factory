import streamlit as st
import google.generativeai as genai
import urllib.parse

# پیج کی سیٹنگ
st.set_page_config(page_title="خودکار بزنس فیکٹری", layout="wide")
st.title("🏭 خودکار بزنس فیکٹری (Multi-AI Engine)")

# ----------------- سائیڈ بار (API Keys کی سیٹنگ) -----------------
st.sidebar.header("🔑 API Keys سیٹنگز")
st.sidebar.write("اپنی دستیاب API Keys نیچے درج کریں:")

# Gemini API Keys
gemini_key_1 = st.sidebar.text_input("Gemini API Key 1", type="password")
gemini_key_2 = st.sidebar.text_input("Gemini API Key 2 (Secondary)", type="password")
gemini_key_3 = st.sidebar.text_input("Gemini API Key 3 (Backup)", type="password")

# دیگر AI سروسز کی Keys
openrouter_key = st.sidebar.text_input("OpenRouter API Key", type="password")
perplexity_key = st.sidebar.text_input("Perplexity API Key", type="password")
openai_key     = st.sidebar.text_input("OpenAI / Microsoft API Key", type="password")
pollinations_key = st.sidebar.text_input("Pollinations Key (Optional)", type="password")

active_gemini_key = gemini_key_1 or gemini_key_2 or gemini_key_3

# ----------------- مین ایپ (Main Application) -----------------
prompt = st.text_input("اپنا بزنس آئیڈیا یا موضوع لکھیں:")

if st.button("بزنس پلان اور ڈیزائن تیار کریں"):
    if not active_gemini_key:
        st.error("براہ کرم سائیڈ بار میں کم از کم ایک Gemini API Key درج کر کے Enter دبائیں!")
    else:
        with st.spinner("آپ کی کی کے مطابق بہترین ماڈل تلاش کیا جا رہا है..."):
            try:
                genai.configure(api_key=active_gemini_key)
                
                # سرور سے خود بخود چیک کریں کہ کون سے ماڈلز دستیاب ہیں
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                if not available_models:
                    model_name = 'gemini-1.5-flash' # بیک اپ نام
                else:
                    # جو بھی پہلا دستیاب ماڈل ہو اسے منتخب کر لیں
                    model_name = available_models[0]
                
                # ماڈل لوڈ کریں اور رسپانس لیں
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(f"Create a detailed business plan for: {prompt}")
                
                if response and response.text:
                    st.success(f"کامیاب! استعمال ہونے والا ماڈل: {model_name}")
                    st.subheader("📊 مارکیٹ تجزیہ و پلان")
                    st.write(response.text)

                    # تصویر تیار کرنا (Pollinations AI)
                    image_prompt = urllib.parse.quote(f"Professional business design for: {prompt}")
                    image_url = f"https://image.pollinations.ai/prompt/{image_prompt}"
                    st.image(image_url, caption="خودکار ڈیزائن (Pollinations AI)")
                else:
                    st.error("ماڈل سے کوئی ڈیٹا موصول نہیں ہوا۔")

            except Exception as e:
                st.error(f"تکنیکی خرابی: {e}")
                st.info("براہ کرم یقینی بنائیں کہ آپ کی API Key درست ہے اور انٹر پریس کیا گیا ہے۔")
