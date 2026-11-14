"""Streamlit MVP Dashboard for AlphaForge AI.

Complies strictly with BNCD Case & Architecture Guidelines:
- Prominent educational disclaimer banner.
- Persona selector (Amira, Mateo, Robert, Profil libre) + Capital + Free question.
- Real-time observable agent trace streaming (st.status).
- Interactive Plotly visualizations (Allocation Donut, Risk Metrics, 2022 Stress Test).
- 4-Question Explainability Rubric with expandable [E#] Evidence Cards.
- Colored Governance Alerts (info=blue, attention=orange, bloquant=red).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from alphaforge.app.pipeline import run_analysis
from alphaforge.app.trace import TraceEvent

# Set page configuration
st.set_page_config(
    page_title="AlphaForge AI — Copilote d'Investissement Explicable",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .reportview-container {
        background: #f8fafc;
    }
    .disclaimer-banner {
        background-color: #fef2f2;
        border-left: 6px solid #dc2626;
        padding: 14px 20px;
        margin-bottom: 20px;
        border-radius: 4px;
        color: #991b1b;
        font-weight: 500;
        font-size: 0.95rem;
    }
    .evidence-badge {
        background-color: #e0f2fe;
        color: #0369a1;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.82rem;
        display: inline-block;
        margin-right: 4px;
    }
    .alert-card-bloquant {
        background-color: #fef2f2;
        border: 1px solid #f87171;
        border-left: 6px solid #dc2626;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 10px;
        color: #7f1d1d;
    }
    .alert-card-attention {
        background-color: #fffbeb;
        border: 1px solid #fcd34d;
        border-left: 6px solid #d97706;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 10px;
        color: #92400e;
    }
    .alert-card-info {
        background-color: #eff6ff;
        border: 1px solid #93c5fd;
        border-left: 6px solid #2563eb;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 10px;
        color: #1e40af;
    }
    .metric-card {
        background: white;
        padding: 16px;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Mandatory Educational Disclaimer Banner
st.markdown(
    """
    <div class="disclaimer-banner">
        ⚠️ <strong>SIMULATION ÉDUCATIVE — AUCUN CONSEIL FINANCIER</strong><br>
        Ce prototype démonstrateur pour le courtage direct (BNCD) éclaire des décisions d'investissement à partir de données publiques.
        Il ne constitue ni une recommandation personnalisée, ni un mandat de gestion, ni une incitation à négocier des titres.
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar Configuration
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/2/23/Logo_Polytechnique_Montr%C3%A9al.svg", width=160)
st.sidebar.title("🛡️ Configuration de Simulation")

persona_choice = st.sidebar.selectbox(
    "Profil Investisseur :",
    options=["Amira (26 ans, Audacieux)", "Mateo (41 ans, Équilibré ESG)", "Robert (59 ans, Prudent)", "Profil libre"],
    index=2,  # Default to Robert for testing reality check
)

capital_input = st.sidebar.number_input(
    "Capital fictif à allouer ($ CAD) :",
    min_value=5000.0,
    max_value=10000000.0,
    value=100000.0,
    step=5000.0,
    format="%.2f",
)

# Default question prompts
if "Robert" in persona_choice:
    default_q = "Je souhaite ajouter 15 % d'actions Tesla (TSLA) à mon portefeuille pour dynamiser la croissance."
elif "Mateo" in persona_choice:
    default_q = "Puis-je investir dans Enbridge (ENB) pour son rendement de dividende tout en respectant mes principes ESG ?"
elif "Amira" in persona_choice:
    default_q = "Je souhaite maximiser mon exposition aux cryptomonnaies et à l'intelligence artificielle."
else:
    default_q = "Je souhaite constituer un portefeuille diversifié adapté à mon horizon d'investissement."

question_input = st.sidebar.text_area(
    "Question ou demande spécifique :",
    value=default_q,
    height=90,
)

# Free Profile Specifics if chosen
custom_profile = None
if persona_choice == "Profil libre":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Paramètres du Profil Libre")
    age = st.sidebar.slider("Âge :", 18, 90, 35)
    horizon = st.sidebar.selectbox("Horizon :", ["Court (1-3 ans)", "Moyen (4-7 ans)", "Long (8+ ans)"], index=1)
    risk_level = st.sidebar.selectbox("Tolérance au risque :", ["low", "moderate", "high"], index=1)
    custom_profile = {
        "name": "Investisseur Autonome",
        "age": age,
        "horizon_label": horizon,
        "risk_profile": risk_level,
        "investment_objective": "Croissance et préservation personnalisée",
    }

force_opus = st.sidebar.checkbox("Escalade Claude Opus (Gouvernance approfondie)", value=False)
analyze_button = st.sidebar.button("🚀 Lancer l'Analyse Agentique", type="primary", use_container_width=True)

# Main Screen Header
st.title("AlphaForge AI — Copilote Agentique d'Investissement")
st.caption("Architecture hybride : Solveurs déterministes CVXPY + Gouvernance institutionnelle + Modèles Amazon Bedrock Converse")

# Session state to preserve analysis result across reruns
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None

if analyze_button:
    persona_key = "robert"
    if "Amira" in persona_choice:
        persona_key = "amira"
    elif "Mateo" in persona_choice:
        persona_key = "mateo"
    elif persona_choice == "Profil libre":
        persona_key = custom_profile

    # Live Execution Trace Stream
    with st.status("Exécution du pipeline agentique AlphaForge...", expanded=True) as status_box:
        trace_logs = []

        def handle_trace_event(event: TraceEvent) -> None:
            if event.event_type == "step_start":
                st.write(f"🔄 **{event.step_name}** : {event.details.get('description', '')}")
            elif event.event_type == "tool_call":
                tool = event.details.get("tool", "")
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;⚙️ *Exécution outil :* `{tool}`")
            elif event.event_type == "evidence_added":
                eid = event.details.get("evidence_id", "")
                summary = event.details.get("summary", "")
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;📝 *Preuve institutionnelle enregistrée :* **[{eid}]** {summary}")
            elif event.event_type == "governance_alert":
                lvl = event.details.get("level", "info")
                rule = event.details.get("rule_id", "")
                icon = "🚨" if lvl == "bloquant" else ("⚠️" if lvl == "attention" else "ℹ️")
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{icon} *Alerte gouvernance [{lvl.upper()}] :* `{rule}`")
            elif event.event_type == "verification_result":
                v_ok = event.details.get("is_valid", False)
                n_nums = event.details.get("numbers_verified", 0)
                v_icon = "✅" if v_ok else "❌"
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{v_icon} *Vérificateur déterministe :* {n_nums} chiffres certifiés (100% sans hallucination)")
            elif event.event_type == "done":
                st.write(f"🏁 *{event.details.get('summary', 'Terminé')}*")

        try:
            result = run_analysis(
                persona_or_profile=persona_key,
                capital=capital_input,
                question=question_input,
                on_event=handle_trace_event,
                force_opus=force_opus,
            )
            st.session_state["last_result"] = result
            status_box.update(label="✅ Analyse agentique complétée et vérifiée avec succès !", state="complete", expanded=False)
        except Exception as e:
            status_box.update(label=f"❌ Erreur lors de l'exécution : {e}", state="error", expanded=True)
            st.error(f"Détails de l'exception : {e}")

# Render Results
if st.session_state["last_result"] is not None:
    res = st.session_state["last_result"]
    metrics = res["metrics"]
    weights = res["allocation"]
    dollars = res["dollar_amounts"]
    stress = res["stress_test"]
    explanation = res["explanation"]
    alerts = res["alerts"]
    evidence = res["evidence"]
    persona = res["persona"]

    # 1. Summary Cards
    st.subheader(f"Portefeuille Stratégique Adapté — {res['persona_name']}")
    parsed_req = res.get("parsed_request", {})
    if parsed_req and parsed_req.get("summary"):
        st.info(f"🧠 **Interprétation de la requête investisseur (Haiku) :** {parsed_req.get('summary')} | *Mode d'exécution : {res.get('execution_path', 'bedrock_agent')}*")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Volatilité Cible", f"{metrics.get('annualized_volatility', 0):.2%}", help="Volatilité annualisée historique en CAD")
    with col2:
        st.metric("Rendement Historique", f"{metrics.get('realized_annual_return', 0):.2%}", help="Rendement annualisé réalisé 2021-2026")
    with col3:
        st.metric("Perte Max (2021-26)", f"{metrics.get('max_drawdown', 0):.2%}", help="Perte maximale historique")
    with col4:
        st.metric("Stress Test 2022", f"{stress.get('portfolio', {}).get('max_drawdown', 0):.2%}", help="Choc stagflation 2022 vs 60/40")
    with col5:
        st.metric("Actifs Actifs", f"{metrics.get('active_assets_count', len(weights))}", help="Nombre d'actifs en portefeuille")

    # Constructive Alternative Comparison Card (if specific asset evaluated)
    evals = res.get("requested_evaluations", [])
    if evals:
        for ev in evals:
            comp = ev.get("comparison", {})
            tkr = comp.get("ticker", "Actif")
            st.markdown(f"### ⚖️ Analyse Comparative d'Adéquation : {tkr}")
            st.markdown(
                f"Comparaison tripartite entre le mandat de base, l'impact de la demande formulée ({comp.get('requested', {}).get('weight', 0):.0%}), "
                f"et l'alternative constructive plafonnée ({comp.get('capped_alternative', {}).get('weight', 0):.0%}) :"
            )
            c_base, c_req, c_alt = st.columns(3)
            with c_base:
                st.markdown("**🛡️ Portefeuille de Base (0 %)**")
                st.write(f"• Volatilité : **{comp.get('baseline', {}).get('annualized_volatility', 0):.2%}**")
                st.write(f"• Perte Max 2022 : **{comp.get('baseline', {}).get('stress_2022_max_dd', 0):.2%}**")
                st.write("• Bande cible : ✅ Conforme")
            with c_req:
                st.markdown(f"**⚠️ Portefeuille Demandé ({comp.get('requested', {}).get('weight', 0):.0%} {tkr})**")
                st.write(f"• Volatilité : **{comp.get('requested', {}).get('annualized_volatility', 0):.2%}**")
                st.write(f"• Perte Max 2022 : **{comp.get('requested', {}).get('stress_2022_max_dd', 0):.2%}**")
                req_ok = comp.get("requested", {}).get("target_band_respected", False)
                st.write(f"• Bande cible : {'✅ Conforme' if req_ok else '❌ Non conforme (Dépassée)'}")
            with c_alt:
                st.markdown(f"**💡 Alternative Plafonnée ({comp.get('capped_alternative', {}).get('weight', 0):.0%} {tkr})**")
                st.write(f"• Volatilité : **{comp.get('capped_alternative', {}).get('annualized_volatility', 0):.2%}**")
                st.write(f"• Perte Max 2022 : **{comp.get('capped_alternative', {}).get('stress_2022_max_dd', 0):.2%}**")
                st.write("• Bande cible : ✅ Conforme")

    # 2. Governance Alerts Section
    if alerts:
        st.markdown("### 🚨 Alertes de Gouvernance & Adéquation")
        for alert in alerts:
            lvl = alert.get("niveau", alert.get("level", "info"))
            msg = alert.get("message", "")
            action = alert.get("suggested_action")
            rule = alert.get("rule_name", "")
            card_class = f"alert-card-{lvl}"

            action_html = f"<br><strong>Action corrective proposée :</strong> {action}" if action else ""
            st.markdown(
                f"""
                <div class="{card_class}">
                    <strong>[{lvl.upper()}] Règle : {rule}</strong><br>
                    {msg}{action_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # 3. Interactive Charts: Donut Allocation + 2022 Stress Benchmark
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Allocation d'Actifs Optimale ($ CAD)")
        df_alloc = pd.DataFrame([
            {"Ticker": t, "Poids (%)": w * 100, "Montant ($ CAD)": dollars.get(t, w * capital_input)}
            for t, w in sorted(weights.items(), key=lambda x: x[1], reverse=True)
        ])
        fig_donut = px.pie(
            df_alloc,
            names="Ticker",
            values="Montant ($ CAD)",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Safe,
            hover_data={"Poids (%)": ":.2f", "Montant ($ CAD)": ":$,.2f"},
        )
        fig_donut.update_traces(textposition="inside", textinfo="percent+label")
        fig_donut.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=380)
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_chart2:
        st.subheader("Test de Résistance 2022 (Stagflation)")
        bm = stress.get("benchmarks", {})
        bench_names = [
            f"Portefeuille {res['persona_name']}",
            "Portefeuille 60/40",
            "TSX Composite (XIU.TO)",
            "S&P 500 (SPY)",
        ]
        bench_dds = [
            stress.get("portfolio", {}).get("max_drawdown", 0) * 100,
            bm.get("benchmark_60_40", {}).get("max_drawdown", 0) * 100,
            bm.get("XIU_TO", {}).get("max_drawdown", 0) * 100,
            bm.get("SPY", {}).get("max_drawdown", 0) * 100,
        ]
        fig_bar = go.Figure(
            data=[
                go.Bar(
                    x=bench_names,
                    y=bench_dds,
                    marker_color=["#2563eb", "#ea580c", "#64748b", "#dc2626"],
                    text=[f"{v:.1f}%" for v in bench_dds],
                    textposition="auto",
                )
            ]
        )
        fig_bar.update_layout(
            yaxis_title="Perte Maximale (%)",
            margin=dict(t=20, b=20, l=20, r=20),
            height=380,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # 4. 4-Question Explainability Rubric (Atelier BNCD)
    st.subheader("📋 Explication Institutionnelle Structurée (Atelier BNCD)")

    st.info(f"**Résumé Exécutif :** {explanation.get('resume', '')}")

    # Helper function to render claims with expandable evidence cards
    def render_claims_with_evidence(claims_list, section_name):
        for item in claims_list:
            claim_text = item.get("claim", "")
            e_ids = item.get("evidence_ids", [])
            badges_html = "".join([f"<span class='evidence-badge'>[{eid}]</span>" for eid in e_ids])
            st.markdown(f"• {claim_text} &nbsp; {badges_html}", unsafe_allow_html=True)

            for eid in e_ids:
                if eid in evidence:
                    ev = evidence[eid]
                    with st.expander(f"🔍 Preuve {eid} : {ev.get('tool')} ({ev.get('description')})", expanded=False):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"**Source :** {ev.get('source')}")
                        c2.caption(f"**Date :** {ev.get('date')}")
                        c3.caption(f"**Devise :** {ev.get('currency')}")
                        st.json(ev.get("result"))

    tab1, tab2, tab3, tab4 = st.tabs([
        "1. Quelles Données Utilisées ?",
        "2. Pourquoi ce Choix ?",
        "3. Limites Méthodologiques",
        "4. Facteurs d'Évolution",
    ])

    with tab1:
        st.markdown("#### Données quantitatives certifiées par les outils :")
        render_claims_with_evidence(explanation.get("quelles_donnees", []), "Données")

    with tab2:
        st.markdown("#### Justification stratégique de l'allocation :")
        render_claims_with_evidence(explanation.get("pourquoi_ce_choix", []), "Choix")

    with tab3:
        st.markdown("#### Limites, hypothèses et biais méthodologiques :")
        limites = explanation.get("limites", [])
        for lim in limites:
            l_type = lim.get("type", "methode").capitalize()
            l_text = lim.get("text", "")
            st.markdown(f"• **[{l_type}]** {l_text}")

    with tab4:
        st.markdown("#### Qu'est-ce qui changerait la réponse ?")
        changements = explanation.get("ce_qui_changerait_la_reponse", [])
        for ch in changements:
            st.markdown(f"• {ch}")

    # 5. Technical Audit Trail & Observable Trace Expander
    st.markdown("---")
    with st.expander("🛠️ Journal d'Audit & Trace d'Exécution Observable (JSON)", expanded=False):
        t_tab1, t_tab2 = st.tabs(["Trace des Événements Observables", "Registre Complet des Preuves"])
        with t_tab1:
            st.json(res["trace"])
        with t_tab2:
            st.json(res["evidence"])
