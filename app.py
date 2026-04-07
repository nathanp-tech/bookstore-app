import streamlit as st
import pandas as pd
import json
import os
from openai import OpenAI
from pypdf import PdfReader
from datetime import datetime
from dotenv import load_dotenv

# --- CHARGEMENT DES PARAMÈTRES DE SÉCURITÉ ---
load_dotenv()  # Charge le fichier .env local

# Priorité : Secrets Streamlit (Cloud) > Environnement (Local .env)
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

# --- CONFIGURATION DU FORMAT ---
COLUMNS_TEMPLATE = [
    'N° chrono', 'Date de réception', 'Date de facture', 'Fournisseurs', 'N° facture', 
    ' HT Exo ', ' HT 2,10% ', ' TVA 2,10% ', ' HT 5,5% ', ' TVA 5,50% ', ' HT 10% ', 
    ' TVA 10% ', ' HT 20% ', ' TVA 20% ', ' Total HT ', ' Total TVA ', ' Total TTC ', 
    'Échéance', 'Payée le', 'Mode de paiement', 'Vu bq', 'N°', 'Année', 'Mois', "Mois d'échéance"
]

def extract_pdf_text(file):
    text = ""
    try:
        reader = PdfReader(file)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted: text += extracted + "\n"
    except Exception as e:
        st.error(f"Erreur lecture PDF : {e}")
    return text

def generate_compta_response(client, pdf_content):
    system_prompt = {
        "role": "system",
        "content": (
            "Tu es un expert comptable pour une librairie. Analyse la facture et extrait les données pour le CSV. "
            "Si une info manque, laisse vide. Pour les montants, n'inclus que le chiffre (ex: 33.90). "
            f"Clés JSON attendues : {COLUMNS_TEMPLATE} + 'Note_IA'."
        )
    }

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[system_prompt, {"role": "user", "content": pdf_content}],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    return json.loads(response.choices[0].message.content)

# --- INTERFACE ---
st.set_page_config(page_title="Compta Librairie Pro", page_icon="🧾", layout="wide")
st.title("📚 Assistant Comptable")

if not api_key:
    st.error("⚠️ Clé API manquante. Configurez le fichier .env ou les Secrets Streamlit.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Paramètres")
    last_chrono = st.number_input("Dernier N° Chrono (ex: 496)", value=496)

uploaded_files = st.file_uploader("Factures PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    client = OpenAI(api_key=api_key)
    
    if st.button("🚀 Analyser"):
        results = []
        logs = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            text_content = extract_pdf_text(file)
            if text_content:
                with st.spinner(f"Analyse : {file.name}"):
                    data = generate_compta_response(client, text_content)
                    if "error" not in data:
                        data['N° chrono'] = f"26/{last_chrono + idx + 1}"
                        # Calcul automatique des dates
                        try:
                            if data.get('Date de facture'):
                                date_obj = datetime.strptime(data['Date de facture'], "%d.%m.%Y")
                                data['Année'], data['Mois'] = date_obj.year, date_obj.month
                            if data.get('Échéance'):
                                data["Mois d'échéance"] = datetime.strptime(data['Échéance'], "%d.%m.%Y").month
                        except: pass
                        
                        note = data.pop("Note_IA", "OK")
                        logs.append({"file": file.name, "note": note})
                        results.append(data)
            progress_bar.progress((idx + 1) / len(uploaded_files))

        if results:
            df = pd.DataFrame(results).reindex(columns=COLUMNS_TEMPLATE)
            st.success("Extraction terminée !")
            st.dataframe(df)
            csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("📥 Télécharger CSV", data=csv, file_name="import_compta.csv", mime="text/csv")
            
            with st.expander("💬 Commentaires de l'IA"):
                for log in logs: st.write(f"**{log['file']}**: {log['note']}")