import streamlit as st
import pandas as pd
import json
import os
from openai import OpenAI
from pypdf import PdfReader
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURATION SÉCURITÉ ---
load_dotenv()
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

# --- INITIALISATION DE L'ÉTAT (SESSION STATE) ---
if 'df_result' not in st.session_state:
    st.session_state.df_result = None
if 'logs' not in st.session_state:
    st.session_state.logs = []

# --- INTERFACE & DESIGN ---
st.set_page_config(
    page_title="Gestion Comptable | Nouveau Chapitre",
    page_icon="📚",
    layout="wide"
)

# CSS pour le look moderne
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    .main { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGO ET TITRE ---
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=150)
    else:
        st.title("📚")
with col_title:
    st.title("Interface Comptable Intelligente")
    st.write("Librairie Nouveau Chapitre — Conservation des données après téléchargement")

st.divider()

# --- PARAMÈTRES CSV ---
COLUMNS_TEMPLATE = [
    'N° chrono', 'Date de réception', 'Date de facture', 'Fournisseurs', 'N° facture', 
    ' HT Exo ', ' HT 2,10% ', ' TVA 2,10% ', ' HT 5,5% ', ' TVA 5,50% ', ' HT 10% ', 
    ' TVA 10% ', ' HT 20% ', ' TVA 20% ', ' Total HT ', ' Total TVA ', ' Total TTC ', 
    'Échéance', 'Payée le', 'Mode de paiement', 'Vu bq', 'N°', 'Année', 'Mois', "Mois d'échéance"
]

# --- FONCTIONS ---
def extract_pdf_text(file):
    text = ""
    try:
        reader = PdfReader(file)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted: text += extracted + "\n"
    except Exception as e:
        st.error(f"Erreur PDF : {e}")
    return text

def generate_compta_response(client, pdf_content):
    system_prompt = {
        "role": "system",
        "content": f"Tu es un expert comptable. Extrait les données. Format dates: JJ.MM.AAAA. Clés JSON: {COLUMNS_TEMPLATE} + 'Note_IA'."
    }
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[system_prompt, {"role": "user", "content": pdf_content}],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    return json.loads(response.choices[0].message.content)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    last_chrono = st.number_input("Dernier N° Chrono", value=496)
    st.divider()
    if st.button("🗑️ NOUVELLE SAISIE (Effacer tout)"):
        st.session_state.df_result = None
        st.session_state.logs = []
        st.rerun()

# --- ZONE DE TRAVAIL ---
if st.session_state.df_result is None:
    # Mode Saisie
    uploaded_files = st.file_uploader("📂 Déposez vos factures PDF ici", type="pdf", accept_multiple_files=True)
    
    if uploaded_files and st.button("🚀 LANCER L'ANALYSE"):
        client = OpenAI(api_key=api_key)
        results = []
        tmp_logs = []
        
        progress_bar = st.progress(0)
        for idx, file in enumerate(uploaded_files):
            text = extract_pdf_text(file)
            if text:
                data = generate_compta_response(client, text)
                data['N° chrono'] = f"26/{last_chrono + idx + 1}"
                # Calcul auto des dates
                try:
                    if data.get('Date de facture'):
                        dt = datetime.strptime(data['Date de facture'], "%d.%m.%Y")
                        data['Année'], data['Mois'] = dt.year, dt.month
                except: pass
                
                tmp_logs.append({"file": file.name, "note": data.pop("Note_IA", "Extraction OK")})
                results.append(data)
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        if results:
            st.session_state.df_result = pd.DataFrame(results).reindex(columns=COLUMNS_TEMPLATE)
            st.session_state.logs = tmp_logs
            st.rerun()

else:
    # Mode Affichage (Persistant après téléchargement)
    st.success("✅ Analyse terminée. Le tableau est conservé ci-dessous.")
    
    st.subheader("📋 Données extraites")
    st.dataframe(st.session_state.df_result, use_container_width=True)

    # Exportation
    csv = st.session_state.df_result.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 TÉLÉCHARGER LE CSV",
        data=csv,
        file_name=f"import_compta_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
    
    st.divider()
    st.subheader("💬 Rapport de l'assistant")
    for log in st.session_state.logs:
        with st.chat_message("assistant"):
            st.write(f"**{log['file']}**")
            st.caption(log['note'])