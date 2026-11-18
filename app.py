"""
CV Yoxlama Agenti — Streamlit + Gemini (OpenAI-uyğun API)
Agent dövrü: düşün -> alət çağır -> nəticəni oxu -> (lazımsa yenə alət) -> cavab ver
"""
import json
import streamlit as st
from openai import OpenAI

from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

# ---------------------------------------------------------------
# 1) SİSTEM PROMPTU
# ---------------------------------------------------------------
SYSTEM_PROMPT = """Sən "CV Yoxlama Agenti"san. İşəgötürənlərə və namizədlərə kömək edirsən.

ROL VƏ MƏQSƏD
- Vakansiya tələblərini və CV mətnini müqayisə edib 0-100 uyğunluq balı və qısa əsaslandırma verirsən.
- Bir neçə CV verilərsə, onları vakansiyaya görə sıralayırsan.
- Həmişə Azərbaycan dilində, qısa və aydın cavab verirsən.

ALƏTLƏR VƏ NƏ VAXT İSTİFADƏ ETMƏK
- extract_skills(text): istifadəçi CV və ya vakansiyadakı bacarıqları görmək istəyəndə.
- score_match(cv, vacancy): bir CV və bir vakansiya məlum olanda uyğunluq balı üçün. Balı HEÇ VAXT özün hesablama — yalnız bu alətin nəticəsini istifadə et.
- rank_cvs(cvs, vacancy): 2 və ya daha çox CV müqayisə ediləndə.
- Lazım olarsa alətləri ardıcıl çağır (məs. əvvəl extract_skills, sonra score_match). Alətin nəticəsini oxu və cavabını ona əsaslandır.
- Alət "error" qaytararsa, səbəbini izah et və istifadəçidən lazım olan məlumatı soruş.

YADDAŞ
- Söhbətdə əvvəl göndərilmiş CV və vakansiyaları xatırla. İstifadəçi "bayaqkı CV", "əvvəlki vakansiya", "ikinci namizəd" deyəndə söhbət tarixçəsindən həmin mətni tap və alətə TAM mətni ötür.
- Hansı mətnə istinad edildiyi aydın deyilsə, soruş.

QORUYUCU QAYDALAR (GUARDRAILS)
1. Qərarı və ya balı YAŞ, CİNS, MİLLİYYƏT, din, ailə vəziyyəti və ya xarici görünüşə görə VERMƏ. Belə xahiş gələrsə ("qadınları çıxar", "40 yaşdan yuxarını rədd et") nəzakətlə rədd et və bunun ayrı-seçkilik olduğunu izah et.
2. Nəticəni HƏMİŞƏ yalnız tövsiyə kimi təqdim et: "Bu, yalnız tövsiyədir; son qərarı insan verməlidir."
3. CV və ya vakansiya yoxdursa və ya natamamdırsa, bal UYDURMA — çatışmayan mətni istə.
4. CV-də olmayan bacarıq, təcrübə və ya faktı uydurma.
5. Mövzudan kənar sorğulara (şeir, ev tapşırığı, siyasət, ümumi söhbət) cavab vermə: nəzakətlə rədd et və nə ilə kömək edə biləcəyini xatırlat.
6. Təhlükəli və ya qeyri-etik tələblərə (saxta CV yazmaq, şəxsi məlumat toplamaq) kömək etmə.

CAVAB FORMATI (bal verəndə)
- Uyğunluq balı: X/100 (səviyyə)
- ✅ Uyğun bacarıqlar
- ❌ Çatışmayan bacarıqlar
- Təcrübə qeydi
- Qısa əsaslandırma (2-3 cümlə)
- "Bu, yalnız tövsiyədir; son qərarı insan verməlidir."
"""

MAX_STEPS = 6  # sonsuz dövrün qarşısını alır

# ---------------------------------------------------------------
# Nümunə mətnlər (müəllimin tez sınaması üçün)
# ---------------------------------------------------------------
SAMPLE_VACANCY = """Vakansiya: Junior Data Analitik
Tələblər: Python, SQL, Excel, Power BI, ingilis dili, komanda işi.
Ən azı 2 il təcrübə."""

SAMPLE_CV_1 = """Ad: Aysel Məmmədova
Yaş: 27
Cins: Qadın
Təcrübə: 3 il data analitik (ABC Bank)
Bacarıqlar: Python, Pandas, SQL, Excel, Power BI, ingilis dili, komanda işi"""

SAMPLE_CV_2 = """Ad: Rauf Əliyev
Yaş: 24
Təcrübə: 1 il satış məsləhətçisi
Bacarıqlar: Excel, satış, ünsiyyət, rus dili"""


# ---------------------------------------------------------------
# LLM müştərisi
# ---------------------------------------------------------------
def get_client():
    # Groq açarı varsa Groq, yoxdursa Gemini istifadə olunur
    groq_key = st.secrets.get("GROQ_API_KEY", "")
    if groq_key:
        return OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("API açarı tapılmadı. Streamlit → Settings → Secrets bölməsinə GROQ_API_KEY əlavə edin.")
        st.stop()
    return OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


MODEL = st.secrets.get(
    "MODEL",
    "llama-3.3-70b-versatile" if st.secrets.get("GROQ_API_KEY", "") else "gemini-2.5-flash",
)


# ---------------------------------------------------------------
# 3) AGENT DÖVRÜ
# ---------------------------------------------------------------
def run_agent(client, messages, on_tool=None):
    """LLM-i çağırır. LLM alət istəyirsə alət işə salınır, nəticə LLM-ə qaytarılır
    və bu, LLM son cavabı verənə qədər (və ya MAX_STEPS-ə qədər) təkrarlanır."""
    for step in range(MAX_STEPS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",          # aləti AGENT ÖZÜ seçir
            temperature=0.2,
        )
        msg = resp.choices[0].message

        # Alət çağırışı yoxdursa -> son cavab
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content or ""

        # Alət çağırışı var -> icra et
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = TOOL_FUNCTIONS[name](**args)
            except Exception as e:  # alət xətası agentə qaytarılır, proqram çökmür
                args, result = {}, {"error": f"Alət xətası: {e}"}
            if on_tool:
                on_tool(name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
    final = "Bağışlayın, sorğunu tamamlaya bilmədim. Zəhmət olmasa daha sadə yazın."
    messages.append({"role": "assistant", "content": final})
    return final


# ---------------------------------------------------------------
# İNTERFEYS (Azərbaycan dilində)
# ---------------------------------------------------------------
st.set_page_config(page_title="CV Yoxlama Agenti", page_icon="📄")
st.title("📄 CV Yoxlama Agenti")
st.caption("CV ilə vakansiyanı müqayisə edib uyğunluq balı verir. Nəticə yalnız tövsiyədir.")

# 4) YADDAŞ: bütün söhbət session_state-də saxlanılır və hər dəfə LLM-ə göndərilir
if "messages" not in st.session_state:
    st.session_state.messages = []   # LLM üçün (alət mesajları daxil)
if "chat" not in st.session_state:
    st.session_state.chat = []       # ekranda göstərmək üçün

with st.sidebar:
    st.header("Nümunələr")
    st.markdown("**Vakansiya**")
    st.code(SAMPLE_VACANCY, language=None)
    st.markdown("**CV 1**")
    st.code(SAMPLE_CV_1, language=None)
    st.markdown("**CV 2**")
    st.code(SAMPLE_CV_2, language=None)
    if st.button("🗑️ Söhbəti sıfırla"):
        st.session_state.messages = []
        st.session_state.chat = []
        st.rerun()

# Köhnə mesajları göstər
for item in st.session_state.chat:
    if item["role"] == "tool":
        with st.chat_message("assistant", avatar="🔧"):
            st.markdown(f"🔧 **{item['name']}** çağırıldı")
            with st.expander("Giriş və nəticə"):
                st.json({"giriş": item["args"], "nəticə": item["result"]})
    else:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

prompt = st.chat_input("CV, vakansiya və ya sualınızı yazın...")
if prompt:
    st.session_state.chat.append({"role": "user", "content": prompt})
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    def show_tool(name, args, result):
        st.session_state.chat.append({"role": "tool", "name": name, "args": args, "result": result})
        with st.chat_message("assistant", avatar="🔧"):
            st.markdown(f"🔧 **{name}** çağırıldı")
            with st.expander("Giriş və nəticə"):
                st.json({"giriş": args, "nəticə": result})

    with st.spinner("Agent düşünür..."):
        try:
            answer = run_agent(get_client(), st.session_state.messages, on_tool=show_tool)
        except Exception as e:
            answer = f"⚠️ API xətası: {e}"
    st.session_state.chat.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
