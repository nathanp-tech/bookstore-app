import streamlit as st
import pandas as pd
import json
import os
from openai import OpenAI
import fitz  # PyMuPDF
import base64
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Libraire Nouveau Chapitre",
    page_icon="📚",
    layout="wide"
)

# --- SÉCURITÉ & CLÉ API ---
load_dotenv()

def get_api_key():
    try:
        # Priorité aux secrets Streamlit (Cloud)
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except:
        pass
    # Repli sur le fichier .env (Local)
    return os.getenv("OPENAI_API_KEY")

api_key = get_api_key()

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
    .stButton>button { 
        width: 100%; border-radius: 8px; font-weight: bold; 
        background-color: #1E3A8A; color: white; border: none; height: 3em;
    }
    .stButton>button:hover { background-color: #3B82F6; }
    .stDataFrame { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- EN-TÊTE ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=120)
    else:
        st.title("📚")
with col_title:
    st.title("Libraire Nouveau Chapitre - Interface Comptable")

st.divider()

# --- STRUCTURE CSV (Stricte conformité avec le fichier Suivi des fournisseurs) ---
COLUMNS_TEMPLATE = [
    'N° chrono', 'Date de réception', 'Date de facture', 'Fournisseurs', 'N° facture', 
    ' HT Exo ', ' HT 2,10% ', ' TVA 2,10% ', ' HT 5,5% ', ' TVA 5,50% ', ' HT 10% ', 
    ' TVA 10% ', ' HT 20% ', ' TVA 20% ', ' Total HT ', ' Total TVA ', ' Total TTC ', 
    'Échéance', 'Payée le', 'Mode de paiement', 'Vu bq', 'N°', 'Année', 'Mois', "Mois d'échéance"
]

# --- LISTE DES FOURNISSEURS ---
KNOWN_SUPPLIERS = [
    "2DCOM", "A VUE D'ŒIL", "ACCES EDITIONS", "AHI33", "AIR FROID", "ALG CLEAN", "ARTODANCE", 
    "AU JARDIN D'ALICE", "AUX EDITIONS DU PHARE", "AVEM", "AVM DIFFUSION", "BELLES LETTRES", 
    "BOREAL", "BREVO", "BRUDIS", "BUREAU VALLEE", "CABAIA", "CAIRN", "CENTRE DES FINANCES PUBLIQUES", 
    "COMPAGNIE 3 CHARDONS", "CYBER SCRIBE FRANCE", "DARUMA SUSHI", "DATALIB", "DG DIFFUSION", 
    "DIFFU-G", "DILICOM", "DILISCO", "DJECO", "DNM", "DOD&CIE", "DRAGONS LUTINES ET COMPAGNIE", 
    "E.LECLERC", "EAU BORDEAUX METROPOLE", "EDF", "EDITIONS DU BORD DU LOT", "EDITIONS DU BRIGADIER", 
    "EDITIONS DU DESASTRE", "EDITIONS FRISON ROCHE", "EDITIONS HOH", "EDITIONS LA LIBRAIRIE DES TERRITOIRES", 
    "EDITIONS LA RAVINIERE", "EDITIONS LETTMOTIFF", "EDITIONS NUAGE", "EDITIONS PASSIFLORE", 
    "EFFIA BASSINS A FLOT", "EI DOMINIQUE ESSE", "FIDALLIANCE", "FLAMMARION", "FONCIA", "GEODIS", 
    "GESTE EDITIONS", "GIGAMIC", "GRINALBERT POLYMEDIA", "HACHETTE", "HARMONIA MUNDI LIVRE SA", 
    "IDP HOME VIDEO", "IMMATERIEL.COM", "IN OCTAVO EDITIONS", "INTERART", "INTERFORUM", "INTERMARCHE", 
    "KAPPUCCINO", "L'ATELIER DU PAPIER", "L'HARMATTAN", "LA GENERALE LIBREST", "LA POSTE", "LE FESTIN", 
    "LE TALMELIER", "LEGAMI", "LES PETITES ALLEES IMPRIM17", "LIBRAIRIE & EDITION YOU-FENG", 
    "LIBRAIRIE J. VRIN", "LIZIA", "MAKASSAR", "MDS", "MYOSIRIS DIFFUSION", "OLF", "OPCO EP", "ORANGE", 
    "PATCHWORK", "PB DEVELOPPEMENT", "PHENICIA", "PIPERNO", "PLM DIFFUSION", "POLLEN", "PROJESTION", 
    "RAGAZZI DA PEPPONE", "SCUDERY EDITIONS", "SERENDIP", "SERVICE HISTORIQUE DE LA DEFENSE", "SIDE", 
    "SODIS", "SOFIA", "SPAR", "YAKABOOKS"
]

# --- FONCTIONS ---
def extract_pdf_images(file):
    images_base64 = []
    try:
        file_bytes = file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Zoom x2 pour la lisibilité
            img_bytes = pix.tobytes("jpeg")
            images_base64.append(base64.b64encode(img_bytes).decode('utf-8'))
        doc.close()
        file.seek(0)
    except Exception as e:
        st.error(f"Erreur lors de la conversion du PDF en image : {e}")
    return images_base64

def generate_compta_response(client, images_base64):
    suppliers_str = ", ".join(KNOWN_SUPPLIERS)
    # Prompt configuré pour utiliser le CSV de référence et éviter les erreurs de fournisseur
    system_prompt = {
        "role": "system",
        "content": (
            "Tu es un expert comptable pour la librairie 'Nouveau Chapitre'. "
            "Ta mission est d'extraire les données d'un document (fourni sous forme d'images) pour un tableau de suivi.\n\n"
            "DIRECTIVES DE RÉFÉRENCE (IMPÉRATIF) :\n"
            "1. FOURNISSEUR : Identifie l'entité qui vend. Le fournisseur est souvent l'information la plus mise en avant sur la facture (logo, texte de grande taille, en-tête). "
            f"Voici une liste de fournisseurs déjà identifiés : {suppliers_str}. "
            "Si le fournisseur correspond à l'un d'eux, utilise exactement ce nom. Si aucun ne correspond, tu dois IMPÉRATIVEMENT écrire le nom identifié en MAJUSCULES. "
            "Interdiction formelle de mettre 'Nouveau Chapitre' ou 'EURL Nouveau Chapitre' dans la colonne 'Fournisseurs'. "
            "Ignore également les noms de banques ou terminaux de paiement (ex: Intesa San Paolo, SumUp, Ingenico).\n"
            "2. VENTILATION TVA : Analyse les taux appliqués. "
            "Si la TVA est de 5,5%, remplis exclusivement ' HT 5,5% ' et ' TVA 5,50% '. "
            "Si c'est du 20%, remplis ' HT 20% ' et ' TVA 20% '. Utilise les colonnes exactes du modèle.\n"
            "3. FORMATS ET DATES : Dates en JJ.MM.AAAA. Montants numériques (virgule ou point). Si une date de réception est trouvée sur le document, il faut utiliser cette date pour la 'Date de facture'.\n"
            "4. MODE DE PAIEMENT : Les seules options possibles sont 'CB', 'LCR', 'PRVT' (pour les prélèvements, par exemple SEPA Direct Debit), ou 'VIREMENT'. N'utilise aucune autre valeur.\n"
            f"Renvoie uniquement un JSON avec ces clés : {COLUMNS_TEMPLATE} + 'Note_IA'."
        )
    }

    user_content = [{"type": "text", "text": "Analyse ces images de facture et extrais les informations demandées au format JSON."}]
    for base64_image in images_base64:
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[system_prompt, {"role": "user", "content": user_content}],
        response_format={"type": "json_object"},
        temperature=0
    )
    return json.loads(response.choices[0].message.content)

# --- NAVIGATION SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    last_chrono = st.number_input("Dernier N° Chrono", value=496)
    
    st.divider()
    menu = st.radio("Navigation", ["📥 Nouvelle Saisie", "📜 Historique"])
    
    if st.button("🗑️ Réinitialiser la session"):
        st.session_state.df_result = None
        st.session_state.logs = []
        st.rerun()

# --- LOGIQUE PRINCIPALE ---
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
                images_base64 = extract_pdf_images(file)
                if images_base64:
                    with st.spinner(f"Analyse de {file.name}..."):
                        data = generate_compta_response(client, images_base64)
                        data['N° chrono'] = f"26/{last_chrono + idx + 1}"
                        # Logique de calcul des colonnes temporelles pour Excel
                        try:
                            if data.get('Date de facture'):
                                dt = datetime.strptime(data['Date de facture'], "%d.%m.%Y")
                                data['Année'], data['Mois'] = str(dt.year), str(dt.month)
                            if data.get('Échéance'):
                                data["Mois d'échéance"] = str(datetime.strptime(data['Échéance'], "%d.%m.%Y").month)
                        except: pass
                        
                        tmp_logs.append({"file": file.name, "note": data.pop("Note_IA", "Extraction OK")})
                        results.append(data)
                bar.progress((idx + 1) / len(uploaded_files))
            
            if results:
                # Sécurisation des types pour l'affichage (Arrow compatible)
                st.session_state.df_result = pd.DataFrame(results).reindex(columns=COLUMNS_TEMPLATE).astype(str)
                st.session_state.logs = tmp_logs
                st.session_state.history.append({
                    "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "df": st.session_state.df_result,
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

elif menu == "📜 Historique":
    st.subheader("Historique des sessions")
    if not st.session_state.history:
        st.info("Aucun historique disponible.")
    else:
        for i, entry in enumerate(reversed(st.session_state.history)):
            with st.expander(f"Session du {entry['date']} ({entry['count']} document(s))"):
                st.dataframe(entry['df'], use_container_width=True)
                csv_hist = entry['df'].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(f"Télécharger cet export", data=csv_hist, file_name=f"archive_{i}.csv", key=f"hist_{i}")