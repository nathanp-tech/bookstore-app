import streamlit as st
import pandas as pd
import json
import os
from openai import OpenAI
from pypdf import PdfReader
from datetime import datetime
from dotenv import load_dotenv

# --- SÉCURITÉ & CLÉ API ---
load_dotenv()

def get_api_key():
    # Test des secrets Streamlit (Cloud) sans lever d'erreur si absent
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except:
        pass
    # Repli sur le fichier .env (Local)
    return os.getenv("OPENAI_API_KEY")

api_key = get_api_key()

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Libraire Nouveau Chapitre",
    page_icon="📚",
    layout="wide"
)

# --- ÉTATS DE SESSION (PERSISTANCE) ---
if 'df_result' not in st.session_state:
    st.session_state.df_result = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'history' not in st.session_state:
    st.session_state.history = []

# --- DESIGN CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; background-color: #1E3A8A; color: white; }
    .stDataFrame { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- EN-TÊTE ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=120)
    else:
        st.title("📚")
with col_title:
    st.title("Libraire Nouveau Chapitre - Interface Comptable")

st.divider()

# --- STRUCTURE CSV ---
COLUMNS_TEMPLATE = [
    'N° chrono', 'Date de réception', 'Date de facture', 'Fournisseurs', 'N° facture', 
    ' HT Exo ', ' HT 2,10% ', ' TVA 2,10% ', ' HT 5,5% ', ' TVA 5,50% ', ' HT 10% ', 
    ' TVA 10% ', ' HT 20% ', ' TVA 20% ', ' Total HT ', ' Total TVA ', ' Total TTC ', 
    'Échéance', 'Payée le', 'Mode de paiement', 'Vu bq', 'N°', 'Année', 'Mois', "Mois d'échéance"
]

# --- FONCTIONS UTILES ---
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

# --- NAVIGATION SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    last_chrono = st.number_input("Dernier N° Chrono", value=496)
    
    st.divider()
    menu = st.radio("Navigation", ["📥 Nouvelle Saisie", "📜 Historique des Uploads"])
    
    if st.button("🗑️ Effacer la session en cours"):
        st.session_state.df_result = None
        st.session_state.logs = []
        st.rerun()

# --- CONTENU PRINCIPAL ---
if not api_key:
    st.error("🔑 Clé API manquante. Configurez votre fichier .env ou les Secrets Streamlit.")
    st.stop()

if menu == "📥 Nouvelle Saisie":
    if st.session_state.df_result is None:
        uploaded_files = st.file_uploader("📂 Déposez vos factures PDF", type="pdf", accept_multiple_files=True)
        
        if uploaded_files and st.button("🚀 ANALYSER LES DOCUMENTS"):
            client = OpenAI(api_key=api_key)
            results = []
            tmp_logs = []
            
            bar = st.progress(0)
            for idx, file in enumerate(uploaded_files):
                text = extract_pdf_text(file)
                if text:
                    data = generate_compta_response(client, text)
                    data['N° chrono'] = f"26/{last_chrono + idx + 1}"
                    # Extraction dates auto
                    try:
                        if data.get('Date de facture'):
                            dt = datetime.strptime(data['Date de facture'], "%d.%m.%Y")
                            data['Année'], data['Mois'] = dt.year, dt.month
                    except: pass
                    
                    tmp_logs.append({"file": file.name, "note": data.pop("Note_IA", "Analyse OK")})
                    results.append(data)
                bar.progress((idx + 1) / len(uploaded_files))
            
            if results:
                new_df = pd.DataFrame(results).reindex(columns=COLUMNS_TEMPLATE)
                st.session_state.df_result = new_df
                st.session_state.logs = tmp_logs
                # Sauvegarde automatique dans l'historique
                st.session_state.history.append({
                    "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "df": new_df,
                    "count": len(results)
                })
                st.rerun()
    else:
        st.subheader("📋 Résultats de l'analyse")
        st.dataframe(st.session_state.df_result, use_container_width=True)
        
        csv = st.session_state.df_result.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("📥 Télécharger le CSV", data=csv, file_name="export_compta.csv", mime="text/csv")
        
        with st.expander("💬 Commentaires de l'assistant"):
            for log in st.session_state.logs:
                st.write(f"**{log['file']}** : {log['note']}")

elif menu == "📜 Historique des Uploads":
    st.subheader("Historique des sessions")
    if not st.session_state.history:
        st.info("Aucun historique disponible pour le moment.")
    else:
        for i, entry in enumerate(reversed(st.session_state.history)):
            with st.expander(f"Session du {entry['date']} ({entry['count']} facture(s))"):
                st.dataframe(entry['df'], use_container_width=True)
                csv_hist = entry['df'].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(f"Télécharger cet export (#{i})", data=csv_hist, file_name=f"archive_compta_{i}.csv", key=f"hist_{i}")