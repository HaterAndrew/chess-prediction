"""Generate a 3-page PDF describing the CCA prediction model + blind test results."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = "output/CCA_Prediction_Model.pdf"


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        topMargin=0.35 * inch,
        bottomMargin=0.3 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'Title2', parent=styles['Title'],
        fontSize=14, spaceAfter=0, spaceBefore=0,
    )
    subtitle = ParagraphStyle(
        'Sub', parent=styles['Normal'], fontSize=8.5, alignment=TA_CENTER,
        spaceAfter=3, textColor=HexColor('#555555'),
    )
    h1 = ParagraphStyle(
        'H1', parent=styles['Heading2'],
        fontSize=10, spaceAfter=1, spaceBefore=2,
        textColor=HexColor('#1a1a2e'),
    )
    h2 = ParagraphStyle(
        'H2', parent=styles['Heading3'],
        fontSize=10, spaceAfter=2, spaceBefore=4,
        textColor=HexColor('#16213e'),
    )
    body = ParagraphStyle(
        'Body2', parent=styles['Normal'],
        fontSize=8.5, spaceAfter=2, leading=11,
    )
    eq = ParagraphStyle(
        'Equation', parent=styles['Normal'],
        fontSize=9.5, spaceAfter=1, spaceBefore=1,
        leftIndent=24, fontName='Helvetica-Bold',
        leading=12,
    )
    eq_sm = ParagraphStyle(
        'EqSmall', parent=styles['Normal'],
        fontSize=8.5, spaceAfter=1, spaceBefore=1,
        leftIndent=24, fontName='Helvetica',
        leading=11,
    )
    note = ParagraphStyle(
        'Note', parent=styles['Normal'],
        fontSize=7.5, spaceAfter=1, leading=9,
        textColor=HexColor('#444444'),
    )
    footer = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=7, alignment=TA_CENTER,
        textColor=HexColor('#999999'),
    )

    GRAY = HexColor('#e0e0e0')
    HDR = HexColor('#e8eaf6')

    def styled_table(data, widths, hdr_bg=HDR, font_size=8.5):
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), hdr_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return t

    story = []
    blg = ParagraphStyle(
        'BodyLarge', parent=styles['Normal'],
        fontSize=8.5, spaceAfter=2, leading=11,
    )

    # ── PAGE 1: PLAIN-ENGLISH EXPLANATION (was page 3) ───────
    story.append(Paragraph("CCA Tournament Entry Prediction Model", title_style))
    story.append(Paragraph("A Plain-English Explanation", subtitle))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY))
    story.append(Spacer(1, 4))

    # Three-way comparison table
    cs = ParagraphStyle('CompCell', parent=body, fontSize=7.5, leading=10)
    cs_b = ParagraphStyle('CompCellB', parent=body, fontSize=7.5, leading=10,
                          fontName='Helvetica-Bold')
    comp_hdr = ParagraphStyle('CompHdr', parent=body, fontSize=7.5, leading=10,
                              fontName='Helvetica-Bold',
                              textColor=HexColor('#ffffff'))

    comp_data = [
        [Paragraph('<b>Metric</b>', comp_hdr),
         Paragraph("<b>Dave's Manual Approach</b>", comp_hdr),
         Paragraph("<b>Igor's Ratio Model</b>", comp_hdr),
         Paragraph('<b>New Model (Ours)</b>', comp_hdr)],
        [Paragraph('<b>Method</b>', cs_b),
         Paragraph('Fixed multiplier x current entries; multiplier from days-to-event lookup, chosen subjectively', cs),
         Paragraph('Historical ratio (entries_at_T / final), median across past 4 years', cs),
         Paragraph('Ensemble: ratio-based + Huber regression, T-dependent weighting', cs)],
        [Paragraph('<b>Error Rate</b>', cs_b),
         Paragraph('~20% median (est.)', cs),
         Paragraph('~12-15% median (est.)', cs),
         Paragraph('<b>7.6% median APE</b> (blind tested)', cs)],
        [Paragraph('<b>Prediction Intervals</b>', cs_b),
         Paragraph('None', cs),
         Paragraph('MAE-based error bars; not calibrated intervals', cs),
         Paragraph('Lognormal calibrated 80% CI; <b>91% coverage</b>', cs)],
        [Paragraph('<b>Blind Testing</b>', cs_b),
         Paragraph('No formal backtesting', cs),
         Paragraph('No formal backtesting', cs),
         Paragraph('88 tournament-years, 2023-2025 expanding window', cs)],
        [Paragraph('<b>Limitations</b>', cs_b),
         Paragraph('Multiplier updated by feel; no systematic validation', cs),
         Paragraph('Single-deadline events only; no multi-deadline handling', cs),
         Paragraph('Needs 3+ yrs history; cannot anticipate one-off disruptions', cs)],
    ]
    comp_w = [0.95 * inch, 1.65 * inch, 1.65 * inch, 1.85 * inch]
    comp_table = Table(comp_data, colWidths=comp_w)
    comp_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('BACKGROUND', (0, 1), (0, -1), HexColor('#f5f5f5')),
        ('BACKGROUND', (3, 1), (3, -1), HexColor('#e8f5e9')),
        ('BOX', (0, 0), (-1, -1), 1, HexColor('#1a1a2e')),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>The Core Idea</b>", h1))
    story.append(Paragraph(
        "Every CCA tournament follows a registration curve \u2014 entries trickle in slowly, "
        "then accelerate as the event nears. The model exploits this. If a tournament has "
        "180 entries with 60 days to go, and the same tournament historically had ~170 at "
        "that point and finished with ~900, we expect roughly 900 again. We compute the "
        "<b>ratio</b> of final-to-current entries at the same lead time across all prior "
        "years, average them, and multiply: 180 \u00d7 5 = 900.", blg))

    story.append(Paragraph("<b>Why Two Models?</b>", h1))
    story.append(Paragraph(
        "The ratio approach works great with good history. For newer tournaments or unusual "
        "patterns, we also run a regression \u2014 a best-fit line through all data points. "
        "The final prediction blends both. Close to the event (last few days), we trust "
        "the ratio more (80%) because the current count is highly informative. Months out, "
        "we lean on regression (85%) because the count is still noisy.", blg))

    story.append(Paragraph("<b>Confidence Range &amp; Sanity Checks</b>", h1))
    story.append(Paragraph(
        "Every prediction includes a confidence interval \u2014 a range the actual result "
        "has fallen within about <b>9 out of 10 times</b> in backtesting (intentionally "
        "conservative \u2014 better to be a little wide than a little narrow). It's wider "
        "far from the event and tighter as it approaches. Small adjustments (1\u20135%) "
        "correct for year-over-year trends, historical withdrawals, and near-capacity "
        "dampening. Predictions that drift too far from historical norms are pulled back "
        "via plausibility bounds.", blg))

    story.append(Paragraph("<b>How We Tested It</b>", h1))
    story.append(Paragraph(
        "We never test on data the model has seen. We train through (say) 2023, then predict "
        "every 2024 tournament as if living in early 2024 \u2014 no future information leaks in. "
        "Across <b>88 tournament-years</b>, the median error was <b>7.6%</b> and the confidence "
        "interval captured the true result <b>91% of the time</b>. The gap between median "
        "error (7.6%) and mean error (13.0%) reflects a small number of tournaments with "
        "unusual conditions; most predictions are tighter than the average suggests.", blg))

    story.append(Paragraph("<b>What We Tried and Rejected</b>", h1))
    story.append(Paragraph(
        "We tested several alternatives on the same blind test. None improved accuracy:", blg))

    reject_data = [
        ['Approach', 'Median Error', 'Why It Was Rejected'],
        ['Year-over-year pacing\n(direct blend)',
         '8.5%  (+0.9)',
         'Comparing this year\'s count to last year\'s at the same\n'
         'point added noise \u2014 the ratio model already captures this.'],
        ['Year-over-year pacing\n(dampened)',
         '7.9%  (+0.3)',
         'Even at low weight (15\u201330%), pacing info was redundant\n'
         'with the historical ratios.'],
        ['Recency-weighted ratios',
         '7.8%  (+0.2)',
         'Overweighting the most recent year narrowed the effective\n'
         'sample, crashing CI reliability (82% vs 91%).'],
        ['Log-linear regression',
         '7.9%  (+0.3)',
         'Transforming features to log-space didn\'t improve fit \u2014\n'
         'the relationship is already roughly linear.'],
        ['Aggressive fill-% shrinkage',
         '7.7%  (+0.1)',
         'Shrinking predictions harder when nearly full was neutral\n'
         'at best. Not worth the added complexity.'],
    ]
    rt = Table(reject_data, colWidths=[1.6 * inch, 1.0 * inch, 3.3 * inch])
    rt.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), HDR),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(rt)
    story.append(Spacer(1, 2))

    story.append(Paragraph("<b>Limitations</b>", h1))
    story.append(Paragraph(
        "The model predicts from historical patterns. It cannot anticipate one-off events: "
        "venue changes, competing tournaments on the same weekend, entry fee changes, or "
        "external disruptions. It works best with 3+ years of history \u2014 brand-new events "
        "get wider confidence ranges. <b>This model is a baseline; tournament directors should "
        "apply manual adjustments for known upcoming factors.</b>", blg))

    story.append(Spacer(1, 4))
    story.append(Paragraph("USAREUR-AF Operational Data Team \u2014 March 2026", footer))

    # ── PAGE 2: WORKED EXAMPLE ───────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Worked Example: Chicago Open 2026", title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Input", h1))
    story.append(styled_table(
        [['Family', 'Current Count', 'T (days to end)', 'Event Dates'],
         ['Chicago Open', '180', '62', 'May 21\u201325, 2026']],
        [1.5 * inch, 1.3 * inch, 1.3 * inch, 1.5 * inch],
        font_size=9,
    ))
    story.append(Paragraph(
        "<i>This is a forward-looking estimate; actual results available after May 25, 2026.</i>",
        note))
    story.append(Spacer(1, 3))

    story.append(Paragraph("Step 1 \u2014 Historical Ratios at T \u2248 60", h2))
    story.append(Paragraph(
        "Collect final/count ratios from prior Chicago Open editions:", body))
    story.append(styled_table(
        [['Year', 'Count at T\u224860', 'Final', 'Ratio'],
         ['2022', '168', '944', '5.62'],
         ['2023', '161', '960', '5.96'],
         ['2024', '191', '860', '4.50'],
         ['2025', '188', '899', '4.78']],
        [0.9 * inch, 1.3 * inch, 0.9 * inch, 0.9 * inch],
        font_size=9,
    ))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "Harmonic mean = 4 / (1/5.62 + 1/5.96 + 1/4.50 + 1/4.78) = <b>5.15</b>"
        " &nbsp;&nbsp;\u2192&nbsp;&nbsp; F(ratio) = 180 \u00d7 5.15 = <b>927</b>", eq_sm))

    story.append(Paragraph("Step 2 \u2014 Huber Regression", h2))
    story.append(Paragraph(
        "Per-family regression:  F(reg) = \u03b20 \u00b7 180  +  "
        "\u03b21 \u00b7 62  +  \u03b22  \u2248  <b>907</b>", eq_sm))

    story.append(Paragraph("Step 3 \u2014 Ensemble Blend", h2))
    story.append(Paragraph(
        "At T = 62 (> 28), ratio weight w = 0.15:", body))
    story.append(Paragraph(
        "F(pred) = 0.15 \u00d7 927  +  0.85 \u00d7 907  =  <b>910</b>", eq))

    story.append(Paragraph("Step 4 \u2014 Adjustments", h2))
    story.append(styled_table(
        [['Adjustment', 'Calculation', 'Result'],
         ['Growth trend (\u22123.4%/yr)', '910 \u00d7 (1 + (\u22120.034) \u00b7 0.5)', '894'],
         ['Withdrawal corr. (1.2%)', '894 \u00d7 (1 \u2212 0.012)', '883'],
         ['Plausibility bounds', 'Below 70% of family median (916);\nblend 0.5 \u00d7 883 + 0.5 \u00d7 916', '900']],
        [1.8 * inch, 2.5 * inch, 0.9 * inch],
        font_size=8.5,
    ))
    story.append(Paragraph(
        "The plausibility check prevents the compounding of small adjustments from pushing the "
        "prediction unreasonably far from historical norms. Final point estimate: <b>~908</b> "
        "(after CI re-centering in log-space).", note))
    story.append(Spacer(1, 3))

    story.append(Paragraph("Step 5 \u2014 Confidence Interval", h2))
    story.append(Paragraph(
        "From lognormal fit on log-ratios, calibrated via LOO with T-dependent shrinkage:", body))
    story.append(Paragraph(
        "\u03c3 = std(log(r)) = 0.127 &nbsp;\u2192&nbsp; "
        "raw CI = [788, 1046] &nbsp;\u2192&nbsp; "
        "\u00d7 shrink(0.33 at T\u224860) &nbsp;\u2192&nbsp; <b>CI = [856, 963]</b>", eq_sm))

    story.append(Spacer(1, 8))

    # Final result box
    result_data = [[
        Paragraph("<b>Chicago Open 2026 Prediction</b>",
                   ParagraphStyle('R', parent=body, fontSize=11, alignment=TA_CENTER)),
        Paragraph("<b>908</b> &nbsp;&nbsp;(80% CI: 856 \u2013 963)",
                   ParagraphStyle('R2', parent=body, fontSize=13, alignment=TA_CENTER)),
    ]]
    result_table = Table(result_data, colWidths=[2.5 * inch, 3.5 * inch])
    result_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HDR),
        ('BOX', (0, 0), (-1, -1), 1.5, HexColor('#1a1a2e')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(result_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>YoY context (informational, not used in model):</b> Chicago Open 2025 had "
        "153 entries at T \u2248 62. Current 2026 count of 180 is +17.6% ahead of last "
        "year's pace. 2025 finished at 899.", note))

    story.append(Spacer(1, 8))
    story.append(Paragraph("USAREUR-AF Operational Data Team \u2014 March 2026", footer))

    # ── PAGE 3: TECHNICAL SPECIFICATION (was page 1) ─────────
    story.append(PageBreak())
    story.append(Paragraph("CCA Tournament Entry Prediction Model", title_style))
    story.append(Paragraph(
        "Mathematical Specification &nbsp;\u2014&nbsp; "
        "<i>\"Entries\" = total section registrations (one player in two sections = two entries)</i>",
        subtitle))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY))
    story.append(Spacer(1, 2))

    # 1. Core equation
    story.append(Paragraph("1. Ensemble Equation", h1))
    story.append(Paragraph(
        "The predicted final entry count is a weighted blend of two sub-models:", body))
    story.append(Paragraph(
        "F<font size='7'> pred</font> = w(T) \u00b7 F<font size='7'> ratio</font>"
        "  +  (1 \u2212 w(T)) \u00b7 F<font size='7'> reg</font>", eq))

    story.append(styled_table(
        [['T (days to end)', '\u2264 3', '\u2264 7', '\u2264 28', '> 28'],
         ['w(T) \u2014 ratio weight', '0.80', '0.55', '0.30', '0.15']],
        [1.6 * inch, 0.85 * inch, 0.85 * inch, 0.85 * inch, 0.85 * inch],
    ))
    story.append(Spacer(1, 2))

    # 2. Ratio model
    story.append(Paragraph("2. Historical Ratio Model (Primary)", h1))
    story.append(Paragraph(
        "For each tournament family at lead time T, compute final/current ratios from every "
        "prior year. Central estimate uses the <b>harmonic mean</b> (downweights outlier-high "
        "ratios; sensitive to near-zero ratios):", body))
    story.append(Paragraph(
        "r = Final / Count_at_T &nbsp;&nbsp;&nbsp;\u2192&nbsp;&nbsp;&nbsp;"
        "F<font size='7'> ratio</font> = Current_Count \u00d7 HarmonicMean(r1, r2, \u2026, rn)", eq_sm))
    story.append(Paragraph(
        "When T falls between historical chop points, ratios are blended in log-space via "
        "inverse-distance interpolation.", note))

    # 3. Regression model
    story.append(Paragraph("3. Huber Regression Model (Secondary)", h1))
    story.append(Paragraph(
        "Per-family robust linear regression (Huber loss, \u03b5 = 1.35) trained on all "
        "historical (count, T) \u2192 final pairs. Falls back to a size-matched global "
        "model for unknown families:", body))
    story.append(Paragraph(
        "F<font size='7'> reg</font> = \u03b20 \u00b7 Count_at_T"
        "  +  \u03b21 \u00b7 T  +  \u03b22", eq))

    # 4. Confidence intervals
    story.append(Paragraph("4. Confidence Intervals", h1))
    story.append(Paragraph(
        "Calibrated lognormal prediction intervals. Raw log-ratio CIs are scaled by LOO-calibrated "
        "factor s(T), then compressed by T-dependent shrinkage (ensemble is better-centered than "
        "ratio-only, so ratio-calibrated CIs are too wide):", body))
    story.append(Paragraph(
        "CI = Count \u00d7 exp( \u03bc  \u00b1  t(\u03b1, n\u22121) \u00b7 \u03c3 "
        "\u00b7 \u221a(1 + 1/n) \u00b7 s(T) \u00b7 shrink(T) )", eq_sm))
    story.append(Paragraph(
        "s(T) via binary search on LOO for 80% coverage; shrink(T) = 0.33 at T \u2265 60 "
        "\u2192 0.75 at T &lt; 5. \u03c3 floored via variance regularization (blend with "
        "global \u03c3) for families with \u2264 3 editions.", note))

    # 5. Adjustments
    story.append(Paragraph("5. Sequential Adjustments", h1))
    story.append(styled_table(
        [['Adjustment', 'Trigger', 'Effect'],
         ['Late-surge damping', 'Scholastic families, T > 3',
          'Cap ratio at 1.1 + 0.4 \u00b7 min(T/90, 1)'],
         ['Fill-% shrinkage', 'Count > 60% of family mean',
          'Shrink ratio toward 1.0 (max 20%)'],
         ['Family anchor', 'Count < threshold, T \u2265 42',
          'Blend with 0.6 \u00b7 recent + 0.4 \u00b7 mean final'],
         ['Growth trend', 'T \u2265 7',
          'Multiply by 1 + trend \u00b7 0.5 (capped \u00b115%)'],
         ['Withdrawal correction', 'Historical data available',
          'Reduce by median withdrawal rate'],
         ['Plausibility bounds', 'Pred < 70% of family median',
          'Blend toward historical median'],
         ['Edition widening', '0\u20131 prior editions',
          'Widen CI by 2.5\u00d7 / 1.5\u00d7']],
        [1.4 * inch, 1.6 * inch, 2.7 * inch],
        font_size=7,
    ))

    # 6. Blind testing
    story.append(Paragraph("6. Model Selection &amp; Blind Testing", h1))
    story.append(Paragraph(
        "Validated via <b>expanding-window blind test</b>: train on years \u2264 Y, "
        "predict year Y+1 at each observed lead time. No future data leakage. "
        "88 tournament-years across 2023\u20132025.", body))

    cand_data = [
        ['Configuration', 'MedAPE', 'MAPE', '80% Cov', 'Verdict'],
        ['Harmonic-mean ratio only', '8.2%', '14.8%', '89%', 'Good base, wide CIs'],
        ['+ Huber regression ensemble', '7.6%', '13.0%', '91%', '\u2713 Selected'],
        ['+ YoY pacing (direct blend)', '8.5%', '15.0%', '88%', 'Adds noise'],
        ['+ YoY pacing (dampened)', '7.9%', '14.1%', '89%', 'Marginal harm'],
        ['+ Recency-weighted ratios', '7.8%', '13.4%', '82%', 'CI coverage crash'],
        ['Log-linear regression', '7.9%', '13.5%', '90%', 'No improvement'],
        ['Aggressive fill-% shrink', '7.7%', '13.2%', '90%', 'Neutral \u2192 rejected'],
    ]
    ct = Table(cand_data, colWidths=[2.0 * inch, 0.7 * inch, 0.65 * inch, 0.7 * inch, 1.6 * inch])
    ct.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), HDR),
        ('BACKGROUND', (0, 2), (-1, 2), HexColor('#e8f5e9')),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ALIGN', (1, 0), (3, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    story.append(ct)
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "<b>Selection rule:</b> keep only changes that improve Median APE without "
        "degrading 80% CI coverage below 88%. YoY pacing tested in 5 configs \u2014 all "
        "hurt because the ratio model already captures count-level info implicitly.", note))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "<b>Final (88 tournament-years):</b> "
        "MedAPE <b>7.6%</b> \u00b7 MAPE <b>13.0%</b> \u00b7 "
        "80% CI Coverage <b>91.2%</b> (conservative\u2014intervals wider "
        "than nominal due to compounding adjustments) \u00b7 Mean CI Width <b>239</b>",
        ParagraphStyle('Perf', parent=body, fontSize=7.5, textColor=HexColor('#1a1a2e'),
                       backColor=HexColor('#f0f0f0'), borderPadding=3)))
    story.append(Spacer(1, 2))
    story.append(Paragraph("USAREUR-AF Operational Data Team \u2014 March 2026", footer))

    doc.build(story)
    print(f"PDF saved to {OUTPUT}")


if __name__ == '__main__':
    build_pdf()
