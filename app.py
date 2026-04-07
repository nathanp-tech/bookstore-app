import streamlit as st
import pandas as pd
import json
import io
import os
from openai import OpenAI
from pypdf import PdfReader
from datetime import datetime

# --- CONFIGURATION ---
OPENAI_API_KEY = "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"

# Liste exacte des colonnes de votre fichier de suivi
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
            "Tu es un expert comptable pour une librairie. "
            "Analyse la facture et extrait TOUTES les informations nécessaires pour remplir ce format CSV précis. "
            "Si une information n'est pas présente, laisse une chaîne vide. "
            "Pour les montants, n'inclus que le chiffre (ex: 33.90). "
            "Renvoie UNIQUEMENT un objet JSON avec ces clés exactes : "
            f"{COLUMNS_TEMPLATE} ainsi qu'une clé 'Note_IA' pour tes commentaires."
        )
    }

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_prompt, {"role": "user", "content": pdf_content}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}

# --- INTERFACE ---
st.set_page_config(page_title="Compta Totale Librairie", page_icon="🧾", layout="wide")
st.title("📚 Assistant Comptable : Import Complet")

with st.sidebar:
    st.header("⚙️ Paramètres")
    last_chrono = st.number_input("Dernier N° Chrono (ex: 496)", value=496)
    st.info("L'IA calculera automatiquement l'année et les mois à partir des dates.")

uploaded_files = st.file_uploader("Glissez vos factures PDF ici", type="pdf", accept_multiple_files=True)

if uploaded_files:
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    if st.button("🚀 Analyser les factures"):
        results = []
        logs = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            text_content = extract_pdf_text(file)
            
            if text_content:
                with st.spinner(f"Traitement de {file.name}..."):
                    data = generate_compta_response(client, text_content)
                    
                    if "error" not in data:
                        # 1. Gestion du Chrono
                        data['N° chrono'] = f"26/{last_chrono + idx + 1}"
                        
                        # 2. Logique automatique pour Année/Mois/Echéance (Sécurité)
                        try:
                            if data.get('Date de facture'):
                                date_obj = datetime.strptime(data['Date de facture'], "%d.%m.%Y")
                                data['Année'] = date_obj.year
                                data['Mois'] = date_obj.month
                            if data.get('Échéance'):
                                due_obj = datetime.strptime(data['Échéance'], "%d.%m.%Y")
                                data["Mois d'échéance"] = due_obj.month
                        except:
                            pass # On garde les valeurs de l'IA si le formatage manuel échoue

                        # 3. Nettoyage des notes
                        note = data.pop("Note_IA", "Extraction complète.")
                        logs.append({"file": file.name, "note": note})
                        results.append(data)
            
            progress_bar.progress((idx + 1) / len(uploaded_files))

        if results:
            df = pd.DataFrame(results)
            # On s'assure que toutes les colonnes du template sont présentes et dans l'ordre
            df = df.reindex(columns=COLUMNS_TEMPLATE)
            
            st.success("Extraction terminée !")
            st.dataframe(df, use_container_width=True)

            # Export CSV avec encodage Excel
            csv = df.to_csv(index=False, encoding="utf-8-sig", sep=",").encode("utf-8-sig")
            st.download_button(
                label="📥 Télécharger le fichier pour Excel",
                data=csv,
                file_name=f"import_fournisseurs_{datetime.now().strftime('%d_%m_%y')}.csv",
                mime="text/csv",
            )

            st.divider()
            st.subheader("💬 Rapport de processus (IA)")
            for log in logs:
                with st.expander(f"Détails : {log['file']}"):
                    st.write(log['note'])