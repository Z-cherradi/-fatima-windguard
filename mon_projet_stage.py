import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="FATIMA WindGuard V3",
    layout="wide"
)

st.title("🌬️ FATIMA WindGuard V3")
st.subheader("Détection des arrêts sans justification")

# ==========================
# CHARGEMENT DES FICHIERS
# ==========================
fichier_akhi = st.file_uploader(
    "📂 Charger le fichier AKHI (CSV)",
    type=["csv"]
)

fichier_alarmes = st.file_uploader(
    "📂 Charger le fichier BRUTE MAI (Excel)",
    type=["xlsx", "xls"]
)

# ==========================
# ANALYSE
# ==========================
if fichier_akhi is not None and fichier_alarmes is not None:

    st.info("Analyse en cours...")

    # ==========================
    # LECTURE AKHI
    # ==========================
    df = pd.read_csv(fichier_akhi)
    df.columns = df.columns.str.strip()

    colonne_turbine = None
    colonne_date = None
    colonne_puissance = None
    colonne_vent = None

    for col in df.columns:
        nom = col.lower()
        if "component" in nom:
            colonne_turbine = col
        if "time" in nom:
            colonne_date = col
        if "puissance" in nom or "power" in nom:
            colonne_puissance = col
        if "wind_speed" in nom:
            colonne_vent = col

    if (
        colonne_turbine is None
        or colonne_date is None
        or colonne_puissance is None
        or colonne_vent is None
    ):
        st.error("Colonnes AKHI introuvables. Vérifiez la structure de votre fichier CSV.")
        st.stop()

    df[colonne_date] = pd.to_datetime(df[colonne_date], errors="coerce")
    df[colonne_puissance] = pd.to_numeric(df[colonne_puissance], errors="coerce")
    df[colonne_vent] = pd.to_numeric(df[colonne_vent], errors="coerce")

    df = df.sort_values([colonne_turbine, colonne_date])

    # ==========================
    # DETECTION ARRETS
    # ==========================
    df["Suspicion"] = (df[colonne_vent] > 5) & (df[colonne_puissance] < 10)

    arrets = []

    for turbine, groupe in df.groupby(colonne_turbine):
        groupe = groupe.copy()
        groupe["Bloc"] = (groupe["Suspicion"] != groupe["Suspicion"].shift()).cumsum()

        for _, bloc in groupe.groupby("Bloc"):
            if not bool(bloc["Suspicion"].iloc[0]): 
                continue

            nb_mesures = len(bloc)
            if nb_mesures < 3:  # Au moins 30 minutes d'arrêt continu
                continue

            debut = bloc[colonne_date].iloc[0] 
            fin = bloc[colonne_date].iloc[-1]

            arrets.append(
                {
                    "Turbine": str(turbine),
                    "Début": debut,
                    "Fin": fin,
                    "Durée (min)": nb_mesures * 10,
                    "Vent moyen": round(bloc[colonne_vent].mean(), 2),
                    "Puissance moyenne": round(bloc[colonne_puissance].mean(), 2)
                }
            )

    if not arrets:
        st.success("Aucun arrêt suspect détecté dans les données SCADA.")
        st.stop()

    arrets_df = pd.DataFrame(arrets)

    # ==========================
    # LECTURE ALARMES
    # ==========================
    alarmes = pd.read_excel(fichier_alarmes, header=6)
    alarmes.columns = alarmes.columns.astype(str).str.strip()

    alarmes["ON"] = pd.to_datetime(alarmes["ON"], errors="coerce")
    alarmes["OFF"] = pd.to_datetime(alarmes["OFF"], errors="coerce")

    # Alignement propre des chaînes de caractères pour le croisement
    alarmes["WT_clean"] = alarmes["WT"].astype(str).str.extract(r'(\d+)')
    arrets_df["Turbine_clean"] = arrets_df["Turbine"].astype(str).str.extract(r'(\d+)')

    # ==========================
    # CROISEMENT INTELLIGENT
    # ==========================
    diagnostics = []
    marge_temps = pd.Timedelta(minutes=15)

    for _, arret in arrets_df.iterrows():
        turbine_id = arret["Turbine_clean"]
        debut = arret["Début"]
        fin = arret["Fin"]

        alarmes_turbine = alarmes[alarmes["WT_clean"] == turbine_id]

        trouvee = alarmes_turbine[
            (alarmes_turbine["ON"] <= (fin + marge_temps)) &
            (alarmes_turbine["OFF"] >= (debut - marge_temps))
        ]

        if len(trouvee) > 0:
            colonne_desc = [c for c in trouvee.columns if "desc" in c.lower() or "alarme" in c.lower() or "description" in c.lower()]
            alarme = str(trouvee.iloc[0][colonne_desc[0]]) if colonne_desc else "Code alarme existant" 
            diagnostic = "Arrêt justifié"
        else:
            alarme = "Aucune"
            diagnostic = "Arrêt sans justification"

        diagnostics.append(
            {
                "Turbine": arret["Turbine"],
                "Début": debut,
                "Fin": fin,
                "Durée (min)": arret["Durée (min)"],
                "Vent moyen": arret["Vent moyen"],
                "Puissance moyenne": arret["Puissance moyenne"],
                "Alarme trouvée": alarme,
                "Diagnostic": diagnostic
            }
        )

    resultat = pd.DataFrame(diagnostics)
    df_sans_just = resultat[resultat["Diagnostic"] == "Arrêt sans justification"]

    # ====================================================
    # CRÉATION DES ONGLETS DE NAVIGATION (FILTRES EN HAUT)
    # ====================================================
    st.write("---")
    onglet_global, onglet_sans_just, onglet_courbe, onglet_statistiques = st.tabs([
        "📋 Tous les arrêts", 
        "🚨 Arrêts sans justification", 
        "📈 Courbes d'Analyse (Physique & Temps)", 
        "📊 Statistiques Générales"
    ])

    # ----------------------------------------------------
    # ONGLET 1 : TOUS LES ARRÊTS
    # ----------------------------------------------------
    with onglet_global:
        st.subheader("Registre global des anomalies SCADA")
        c1, c2 = st.columns(2)
        c1.metric("Total arrêts détectés", len(resultat))
        c2.metric("Turbines impactées (Total)", resultat["Turbine"].nunique())
        
        st.dataframe(resultat, use_container_width=True)
        
        csv_all = resultat.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📊 Télécharger le registre complet (CSV)",
            csv_all, "registre_complet.csv", "text/csv", use_container_width=True
        )

    # ----------------------------------------------------
    # ONGLET 2 : ARRÊTS SANS JUSTIFICATION
    # ----------------------------------------------------
    with onglet_sans_just:
        st.subheader("Focus : Arrêts critiques non justifiés")
        c1, c2 = st.columns(2)
        c1.metric("Arrêts sans justification", len(df_sans_just))
        c2.metric("Turbines ciblées", df_sans_just["Turbine"].nunique() if not df_sans_just.empty else 0)
        
        if not df_sans_just.empty:
            st.dataframe(df_sans_just, use_container_width=True)
            
            texte_rapport = f"Nombre d'arrêts sans justification : {len(df_sans_just)}\n\n"
            for _, row in df_sans_just.iterrows():
                texte_rapport += f"- Turbine {row['Turbine']} : du {row['Début']} au {row['Fin']} ({row['Durée (min)']} min)\n"
                
            st.download_button(
                "📄 Télécharger le Rapport Textuel (TXT)",
                texte_rapport.encode("utf-8"), "Rapport_Anomalies.txt", "text/plain", use_container_width=True
            )
        else:
            st.success("Parfait ! Aucun arrêt sans justification sur cette période.")

    # ----------------------------------------------------
    # ONGLET 3 : COURBES D'ANALYSE (SÉPARÉES)
    # ----------------------------------------------------
    with onglet_courbe:
        st.subheader("Visualisation Graphique Avancée")
        
        liste_turbines = sorted(df[colonne_turbine].unique())
        turbine_selectionnee = st.selectbox("Sélectionner une éolienne à analyser :", liste_turbines)
        
        col_courbe_physique, col_frise_temps = st.columns(2)
        
        with col_courbe_physique:
            st.markdown("**1. Courbe de Puissance vs Vent (Analyse Physique)**")
            st.caption("Les points roses représentent les anomalies (Vent fort mais production nulle/faible).")
            
            df_turbine = df[df[colonne_turbine] == turbine_selectionnee].copy()
            
            fig_physique = px.scatter(
                df_turbine,
                x=colonne_vent,
                y=colonne_puissance,
                color="Suspicion",
                color_discrete_map={False: "#1f77b4", True: "#e377c2"},
                labels={"Suspicion": "Anomalie détectée"},
                title=f"Nuage de points - Turbine {turbine_selectionnee}"
            )
            fig_physique.update_layout(xaxis_title="Vitesse du vent (m/s)", yaxis_title="Puissance (kW)")
            st.plotly_chart(fig_physique, use_container_width=True)
            
        with col_frise_temps:
            st.markdown("**2. Chronologie Temporelle des Arrêts (Frise de Gantt)**")
            st.caption("Visualisez la durée exacte et le positionnement dans le temps des plages d'arrêts.")
            
            resultat_filtre = resultat[resultat["Turbine"] == str(turbine_selectionnee)]
            
            if not resultat_filtre.empty:
                fig_gantt = px.timeline(
                    resultat_filtre, 
                    x_start="Début", 
                    x_end="Fin", 
                    y="Turbine", 
                    color="Diagnostic",
                    hover_data=["Durée (min)", "Vent moyen", "Alarme trouvée"],
                    color_discrete_map={"Arrêt justifié": "#2ca02c", "Arrêt sans justification": "#d62728"}
                )
                fig_gantt.update_layout(xaxis_title="Date & Heure", yaxis_title="Machine", showlegend=True)
                st.plotly_chart(fig_gantt, use_container_width=True)
            else:
                st.info(
                    "Aucun arrêt détecté pour cette turbine."
                )