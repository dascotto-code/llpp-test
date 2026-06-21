"""
LLPP Digital Colleague - Versione Finale Enterprise
"""

import os
from io import BytesIO
from datetime import datetime

import streamlit as st
import requests
from PyPDF2 import PdfReader
from docx import Document

# ========== CONFIGURAZIONE ==========
MODEL_NAME = "gemini-1.5-flash"
MAX_CHARS = 500000  

SYSTEM_PROMPT_TEMPLATE = """Sei 'RUP-Digitale', un assistente esperto in Lavori Pubblici italiani.

REGOLA FONDAMENTALE SULLE NORMATIVE STATALI:
Sei vincolato ESCLUSIVAMENTE al D.Lgs. 36/2023 e suoi decreti attuativi. È VIETATO citare o applicare il D.Lgs. 50/2016.

REGOLE INTERNE, DIRETTIVE E LINEE GUIDA DELL'ENTE (PRIORITÀ ASSOLUTA):
Se tra i documenti caricati sono presenti file contenenti regole operative, manuali interni, checklist di fase, o direttive specifiche dell'Ente/Regione, tu DEVI considerare queste regole come VINCOLANTI.
Le procedure interne dell'Ente sovrascrivono le prassi generiche. Devi seguirle alla lettera e citare che lo stai facendo in base a tale direttiva.

STILE E MODELLI DI RIFERIMENTO (FEW-SHOT):
Se tra i documenti caricati ci sono vecchie Determine, Delibere o Atti amministrativi, tu DEVI:
1. Clonare ESATTAMENTE quello schema e quel tono burocratico per il nuovo atto.
2. Sostituire nei modelli solo i dati vecchi con i dati nuovi reperiti negli altri documenti.

CONTESTO ATTUALE (Tutti i file caricati):
{DOCUMENTI_LETTI}

IL TUO COMPITO:
1. ANALISI DI FASE: Identifica lo stato dell'arte secondo l'Art. 23 D.Lgs 36/2023.
2. GAP ANALYSIS: Cosa c'è e cosa manca.
3. GENERAZIONE BOZZA: Redigi il documento richiesto clonando gli esempi e rispettando le regole interne.
4. NORMATIVE: Cita Art. e Comma del D.Lgs. 36/2023.

REGOLE GENERALI:
- Linguaggio burocratico. Niente chiacchiere.
- Se mancano dati, inserisci un placeholder [INSERIRE DATO]."""

# ========== PARSING DOCUMENTI ==========
def extract_text_from_pdf(file_bytes) -> str:
    try:
        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[Errore lettura PDF: {e}]"

def extract_text_from_docx(file_bytes) -> str:
    try:
        doc = Document(BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        return f"[Errore lettura DOCX: {e}]"

def extract_text_from_txt(file_bytes) -> str:
    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"[Errore lettura TXT: {e}]"

def smart_truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    half = MAX_CHARS // 2
    return text[:half] + "\n\n[... CONTENUTO TRONCATO ...]\n\n" + text[-half:]

def process_uploaded_files(uploaded_files):
    documents_info = []
    full_parts = []
    
    for f in uploaded_files:
        ext = os.path.splitext(f.name)[1].lower()
        file_bytes = f.read()
        
        if ext == ".pdf": text = extract_text_from_pdf(file_bytes)
        elif ext in (".docx", ".doc"): text = extract_text_from_docx(file_bytes)
        elif ext == ".txt": text = extract_text_from_txt(file_bytes)
        else: continue
            
        documents_info.append({"name": f.name, "preview": text[:300]})
        full_parts.append(f"--- INIZIO DOCUMENTO: {f.name} ---\n{text}\n--- FINE DOCUMENTO ---\n\n")

    return documents_info, smart_truncate("\n".join(full_parts))

# ========== INTELLIGENZA ARTIFICIALE (GEMINI REST) ==========
def ask_rup_digitale(user_message: str, system_prompt: str, history: list) -> str:
    api_key = st.secrets["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"
    
    contents = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.1, "topP": 0.95}
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except requests.exceptions.HTTPError as e:
        error_msg = e.response.json().get('error', {}).get('message', str(e))
        return f"[Errore API Google: {error_msg}]"
    except Exception as e:
        return f"[Errore generico: {e}]"

def looks_like_draft(text: str) -> bool:
    keywords = ["bozza", "oggetto:", "il sottoscritto", "determina", "premesso", "ritenuto", "art. ", "d.lgs"]
    return any(k in text.lower() for k in keywords)

# ========== INTERFACCIA UTENTE STREAMLIT ==========
st.set_page_config(page_title="LLPP Assistant Pro", page_icon="⚖️", layout="wide")

with st.sidebar:
    st.title("⚖️ LLPP Assistant Pro")
    st.caption("Motore: Gemini 1.5 | Riferimento: D.Lgs. 36/2023 + Regole Ente")
    st.markdown("---")
    
    uploaded_files = st.file_uploader(
        "Carica TUTTO: Progetto + Norme + Regole Interne + Modelli Determine",
        type=["pdf", "docx", "doc", "txt"],
        accept_multiple_files=True
    )
    analyze_btn = st.button("🧠 Analizza e Carica nel Contesto", use_container_width=True)
    
    st.markdown("---")
    with st.expander("💡 Come caricare i file (Best Practice)"):
        st.markdown("""
        Nomina i file in modo esplicito:
        - **Regole interne:** `REGOLA_Manualistica_Affidamenti.docx`
        - **Modelli da clonare:** `ESEMPIO_Determina_2023.docx`
        - **Normativa:** `NORMA_Dlgs_36_2023.pdf`
        - **Progetto:** `Relazione_Tecnica.pdf`
        """)

if "messages" not in st.session_state: st.session_state.messages = []
if "context" not in st.session_state: st.session_state.context = ""
if "documents" not in st.session_state: st.session_state.documents = []
if "system_prompt" not in st.session_state: st.session_state.system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{DOCUMENTI_LETTI}", "[Nessun documento]")

if analyze_btn:
    if not uploaded_files:
        st.error("Carica almeno un file nel riquadro sopra.")
    else:
        with st.spinner("Estrazione testo e allineamento contesto..."):
            docs, ctx = process_uploaded_files(uploaded_files)
            st.session_state.documents = docs
            st.session_state.context = ctx
            st.session_state.system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{DOCUMENTI_LETTI}", ctx)
            st.session_state.messages = [] 
            
        st.success(f"Contesto aggiornato: {len(ctx):,} caratteri. Documenti letti: {len(docs)}.")

st.title("🏗️ Agente di Supporto all'Iter LLPP")

with st.expander(f"📄 Documenti nel Contesto Attuale ({len(st.session_state.documents)})", expanded=False):
    if not st.session_state.documents:
        st.info("Nessun documento caricato.")
    else:
        for d in st.session_state.documents:
            st.markdown(f"**{d['name']}**")
            st.text(d["preview"])
            st.markdown("---")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("has_draft", False):
            st.download_button(label="📥 Scarica Bozza (.md)", data=msg["content"], file_name=f"bozza_{msg['id']}.md", mime="text/markdown", key=f"dl_{msg['id']}")

user_input = st.chat_input("Es: Scrivi la determina seguendo le REGOLE e usando l'ESEMPIO...")
if user_input:
    if not st.session_state.context.strip():
        st.warning("Carica i documenti nella sidebar prima di procedere.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_input, "id": len(st.session_state.messages)})
        with st.chat_message("user"): 
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("RUP-Digitale sta redigendo..."):
                reply = ask_rup_digitale(user_input, st.session_state.system_prompt, st.session_state.messages[:-1])
            st.markdown(reply)
            
            has_draft = looks_like_draft(reply)
            if has_draft:
                st.download_button(label="📥 Scarica Bozza (.md)", data=reply, file_name=f"bozza_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md", mime="text/markdown", key=f"dl_new_{len(st.session_state.messages)}")

        st.session_state.messages.append({"role": "assistant", "content": reply, "has_draft": has_draft, "id": len(st.session_state.messages)})
