"""Pure-Python compliant PDF generator for Suitability Records (PRD B-14, #121).

Generates standard PDF 1.4 documents without requiring heavy C extensions.
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def _escape_pdf_text(text: str) -> str:
    """Escape characters for PDF text literal syntax and sanitize non-ASCII to safe Latin-1."""
    # Convert accented French characters to clean ASCII representations for Standard 14 Fonts
    accents = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
        "É": "E", "È": "E", "Ê": "E", "Ë": "E",
        "À": "A", "Â": "A", "Ä": "A",
        "Î": "I", "Ï": "I",
        "Ô": "O", "Ö": "O",
        "Ù": "U", "Û": "U", "Ü": "U",
        "Ç": "C",
        "’": "'", "«": '"', "»": '"',
        "—": "-", "–": "-",
    }
    clean = ""
    for ch in text:
        if ch in accents:
            clean += accents[ch]
        elif ord(ch) < 128:
            clean += ch
        else:
            clean += " "
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PDFBuilder:
    def __init__(self) -> None:
        self.lines: list[tuple[str, int, float, float, float, float, float]] = []  # (text, font_idx, size, x, y, r, g, b)

    def add_text(
        self,
        text: str,
        x: float,
        y: float,
        font_idx: int = 1,
        size: float = 10,
        r: float = 0.0,
        g: float = 0.0,
        b: float = 0.0,
    ) -> None:
        self.lines.append((text, font_idx, size, x, y, r, g, b))

    def build(self) -> bytes:
        stream_parts = []
        for text, font_idx, size, x, y, r, g, b in self.lines:
            escaped = _escape_pdf_text(text)
            stream_parts.append(f"{r:.2f} {g:.2f} {b:.2f} rg")
            stream_parts.append(f"BT /F{font_idx} {size} Tf {x:.1f} {y:.1f} Td ({escaped}) Tj ET")

        stream_data = "\n".join(stream_parts).encode("latin-1", errors="replace")
        stream_len = len(stream_data)

        objects = []
        # Obj 1: Catalog
        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
        # Obj 2: Pages
        objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
        # Obj 3: Page (Letter 612 x 792)
        objects.append(
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>\nendobj"
        )
        # Obj 4: Contents Stream
        objects.append(
            f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin-1")
            + stream_data
            + b"\nendstream\nendobj"
        )
        # Obj 5: Helvetica (Regular)
        objects.append(
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj"
        )
        # Obj 6: Helvetica-Bold
        objects.append(
            b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj"
        )

        # Assemble PDF with cross-reference table
        output = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        xref_offsets = [0]
        offset = len(output[0])

        for obj in objects:
            xref_offsets.append(offset)
            output.append(obj + b"\n")
            offset += len(obj) + 1

        xref_pos = offset
        output.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        output.append(b"0000000000 65535 f \n")
        for off in xref_offsets[1:]:
            output.append(f"{off:010d} 00000 n \n".encode("latin-1"))

        trailer = (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        )
        output.append(trailer.encode("latin-1"))

        return b"".join(output)


def generate_suitability_pdf(record: dict[str, Any]) -> bytes:
    """Generate official Suitability Record PDF document."""
    pdf = PDFBuilder()

    # Document Header Banner
    pdf.add_text("ALPHAFORGE AI · DOSSIER DE REVUE (SIMULATION EDUCATIVE)", 50, 745, font_idx=2, size=14, r=0.08, g=0.20, b=0.45)
    pdf.add_text("Projet etudiant PolyFinances 2026. Document fictif : aucun conseil personnalise, aucune operation reelle.", 50, 730, font_idx=1, size=9, r=0.6, g=0.1, b=0.1)

    run_id = str(record.get("run_id", "N/A"))
    reviewed_at = str(record.get("reviewed_at", dt.datetime.now(dt.UTC).isoformat()))
    reviewer_id = str(record.get("reviewer_id", "Reviseur"))

    pdf.add_text(f"Identifiant de l'analyse : {run_id}", 50, 705, font_idx=2, size=10)
    pdf.add_text(f"Reviseur : {reviewer_id}", 350, 705, font_idx=2, size=10)
    pdf.add_text(f"Date et heure de validation : {reviewed_at}", 50, 690, font_idx=1, size=9)

    # Horizontal divider line
    pdf.add_text("__________________________________________________________________________________________", 50, 678, font_idx=1, size=8, r=0.7, g=0.7, b=0.7)

    # Section 1: Profil KYC Client
    pdf.add_text("1. PROFIL DE L'INVESTISSEUR & INSTANTANE KYC", 50, 660, font_idx=2, size=11, r=0.08, g=0.20, b=0.45)
    kyc = record.get("kyc_snapshot") or {}
    pdf.add_text(f"Client / Profil : {kyc.get('persona', 'Custom')}", 60, 642, font_idx=1, size=9)
    pdf.add_text(f"Objectif : {kyc.get('objective', 'N/A')}", 220, 642, font_idx=1, size=9)
    pdf.add_text(f"Horizon temporel : {kyc.get('horizon_years', 'N/A')} ans", 400, 642, font_idx=1, size=9)

    pdf.add_text(f"Tolerance au risque : {kyc.get('risk_tolerance', 'N/A')}", 60, 626, font_idx=1, size=9)
    pdf.add_text(f"Capacite financiere : {kyc.get('risk_capacity', 'N/A')}", 220, 626, font_idx=1, size=9)
    pdf.add_text(f"Type de compte : {kyc.get('account_type', 'Non precise')}", 400, 626, font_idx=1, size=9)

    budget = kyc.get("budget_cad")
    budget_str = f"{budget:,.2f} $ CAD" if budget else "Non specifie"
    pdf.add_text(f"Capital simule : {budget_str}", 60, 610, font_idx=1, size=9)

    constraints = kyc.get("constraints") or []
    pdf.add_text(f"Contraintes / Exclusions : {', '.join(constraints) if constraints else 'Aucune'}", 220, 610, font_idx=1, size=9)

    # Section 2: Scénario Retenu & Justification Professionnelle
    pdf.add_text("2. SCENARIO RETENU LORS DE LA REVUE", 50, 580, font_idx=2, size=11, r=0.08, g=0.20, b=0.45)
    chosen = str(record.get("chosen_scenario", "N/A"))
    pdf.add_text(f"Scenario retenu par le conseiller : {chosen.upper()}", 60, 562, font_idx=2, size=10, r=0.1, g=0.5, b=0.2)

    rationale = str(record.get("rationale", "Aucune justification specifiee."))
    pdf.add_text("Justification du reviseur :", 60, 545, font_idx=2, size=9)

    # Wrap rationale text in blocks of 80 chars
    y_pos = 530
    words = rationale.split()
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > 85:
            pdf.add_text(line, 70, y_pos, font_idx=1, size=9)
            y_pos -= 14
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        pdf.add_text(line, 70, y_pos, font_idx=1, size=9)
        y_pos -= 14

    # Section 3: Allocations du scénario retenu
    y_pos -= 10
    pdf.add_text("3. DETAIL DE L'ALLOCATION RETENUE", 50, y_pos, font_idx=2, size=11, r=0.08, g=0.20, b=0.45)
    y_pos -= 18

    scenarios = record.get("scenarios") or []
    chosen_scenario_data = None
    for sc in scenarios:
        if sc.get("name") == chosen:
            chosen_scenario_data = sc
            break

    if chosen_scenario_data and "weights" in chosen_scenario_data:
        weights = chosen_scenario_data["weights"]
        pdf.add_text("Titre / Actif", 70, y_pos, font_idx=2, size=9)
        pdf.add_text("Ponderation recommandee", 250, y_pos, font_idx=2, size=9)
        y_pos -= 14
        for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
            pct_str = f"{float(weight) * 100:.1f} %"
            pdf.add_text(str(ticker), 70, y_pos, font_idx=1, size=9)
            pdf.add_text(pct_str, 250, y_pos, font_idx=1, size=9)
            y_pos -= 12
    else:
        pdf.add_text("Ponderations du scenario enregistrees dans la trace d'audit.", 70, y_pos, font_idx=1, size=9)
        y_pos -= 14

    # Section 4: Contrôles de Conformité & Données
    y_pos -= 10
    pdf.add_text("4. CONTROLES DE CONFORMITE DETERMINISTE & TRACABILITE", 50, y_pos, font_idx=2, size=11, r=0.08, g=0.20, b=0.45)
    y_pos -= 18

    verifier = record.get("verifier_result") or {}
    verif_status = "SUCCES - Verification deterministe passee" if verifier.get("passed") else "NON VERIFIE"
    pdf.add_text(f"Statut verificateur Agent 4 : {verif_status}", 60, y_pos, font_idx=1, size=9)
    y_pos -= 14

    models = record.get("model_ids") or {}
    main_mod = models.get("main", "Bedrock Claude 5.5")
    pdf.add_text(f"Modeles d'IA utilises : {main_mod}", 60, y_pos, font_idx=1, size=9)
    y_pos -= 14

    data_dates = record.get("data_dates") or {}
    as_of = data_dates.get("as_of_date", "Date d'observation courante")
    pdf.add_text(f"Date de reference des donnees financieres : {as_of}", 60, y_pos, font_idx=1, size=9)
    y_pos -= 25

    # Signature Block
    pdf.add_text("ATTESTATION DU CONSEILLER ENREGISTRE :", 50, y_pos, font_idx=2, size=10)
    y_pos -= 14
    pdf.add_text("Je confirme avoir verifie l'adequation de cette recommandation avec la situation personnelle,", 50, y_pos, font_idx=1, size=8, r=0.3, g=0.3, b=0.3)
    y_pos -= 11
    pdf.add_text("les objectifs financiers, la tolerance et la capacite de risque du client conformement a la reglementation.", 50, y_pos, font_idx=1, size=8, r=0.3, g=0.3, b=0.3)
    y_pos -= 20
    pdf.add_text(f"[SIGNE ELECTRONIQUEMENT PAR {reviewer_id.upper()} · LE {reviewed_at}]", 50, y_pos, font_idx=2, size=9, r=0.08, g=0.20, b=0.45)

    return pdf.build()
