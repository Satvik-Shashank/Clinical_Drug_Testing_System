import jsPDF from "jspdf";
import type { HistoryEntry, SafetyCheckResponse } from "./safety-types";

const MARGIN = 14;
const LINE = 5.2;

export function exportSafetyReportPdf(entry: HistoryEntry) {
  const { request, response } = entry;
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  let y = MARGIN;

  function ensureSpace(needed: number) {
    if (y + needed > pageH - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  }

  function setColor(name: "primary" | "danger" | "warning" | "success" | "muted" | "fg") {
    const map = {
      primary: [30, 58, 138],
      danger: [220, 38, 38],
      warning: [245, 158, 11],
      success: [22, 163, 74],
      muted: [107, 114, 128],
      fg: [15, 23, 42],
    } as const;
    const [r, g, b] = map[name];
    doc.setTextColor(r, g, b);
  }

  function setFill(name: "primary" | "danger" | "warning" | "success" | "muted" | "soft") {
    const map = {
      primary: [30, 58, 138],
      danger: [220, 38, 38],
      warning: [245, 158, 11],
      success: [22, 163, 74],
      muted: [243, 244, 246],
      soft: [249, 250, 251],
    } as const;
    const [r, g, b] = map[name];
    doc.setFillColor(r, g, b);
  }

  function drawSectionHeading(text: string) {
    ensureSpace(10);
    setColor("primary");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.text(text.toUpperCase(), MARGIN, y);
    setFill("primary");
    doc.rect(MARGIN, y + 1.5, pageW - MARGIN * 2, 0.4, "F");
    y += 6;
  }

  function drawText(text: string, opts: { bold?: boolean; size?: number; color?: Parameters<typeof setColor>[0] } = {}) {
    doc.setFont("helvetica", opts.bold ? "bold" : "normal");
    doc.setFontSize(opts.size ?? 9.5);
    setColor(opts.color ?? "fg");
    const lines = doc.splitTextToSize(text, pageW - MARGIN * 2);
    for (const line of lines) {
      ensureSpace(LINE);
      doc.text(line, MARGIN, y);
      y += LINE;
    }
  }

  function drawBadge(label: string, tone: "danger" | "warning" | "success" | "primary" | "muted") {
    const w = doc.getTextWidth(label) + 6;
    setFill(tone);
    doc.roundedRect(MARGIN, y - 3.5, w, 5, 1, 1, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(8);
    doc.setTextColor(255, 255, 255);
    doc.text(label, MARGIN + 3, y);
    y += 6;
  }

  // ----- Header -----
  setFill("primary");
  doc.rect(0, 0, pageW, 18, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text("Clinical Drug Safety Report", MARGIN, 11);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  doc.text(
    new Date(entry.timestamp).toLocaleString(),
    pageW - MARGIN,
    11,
    { align: "right" },
  );
  y = 24;

  // Summary
  drawSectionHeading("Summary");
  const riskTone =
    response.overall_risk === "HIGH" ? "danger" : response.overall_risk === "MEDIUM" ? "warning" : "success";
  drawBadge(`OVERALL RISK: ${response.overall_risk}`, riskTone);
  drawText(`Patient Risk Score: ${Math.round(response.patient_risk_score)} / 100`, { bold: true });
  drawText(`Safe to Prescribe: ${response.safe_to_prescribe ? "YES" : "NO"}`);
  drawText(`Requires Doctor Review: ${response.requires_doctor_review ? "TRUE" : "FALSE"}`);
  y += 2;

  // Patient
  drawSectionHeading("Patient & Medication Input");
  drawText(`Medicines: ${request.medicines.join(", ") || "—"}`);
  drawText(`Current Medications: ${request.patient_history.current_medications.join(", ") || "—"}`);
  drawText(`Known Allergies: ${request.patient_history.known_allergies.join(", ") || "—"}`);
  drawText(`Conditions: ${request.patient_history.conditions.join(", ") || "—"}`);
  drawText(`Age: ${request.patient_history.age}    Weight: ${request.patient_history.weight} kg`);
  y += 2;

  // Interactions
  drawSectionHeading(`Drug Interactions (${response.interactions.length})`);
  if (response.interactions.length === 0) {
    drawText("No interactions reported.", { color: "muted" });
  } else {
    for (const i of response.interactions) {
      drawText(`• ${i.drug_a} + ${i.drug_b}  [${i.severity}]`, { bold: true });
      drawText(`  Mechanism: ${i.mechanism}`);
      drawText(`  Recommendation: ${i.recommendation}`);
      y += 1;
    }
  }

  // Allergies
  drawSectionHeading(`Allergy Alerts (${response.allergies.length})`);
  if (response.allergies.length === 0) {
    drawText("No allergy alerts.", { color: "muted" });
  } else {
    for (const a of response.allergies) {
      drawText(`• ${a.drug} ↔ ${a.allergen}  [${a.severity}]`, { bold: true, color: "danger" });
      drawText(`  ${a.reason}`);
    }
  }

  // Contraindications
  drawSectionHeading(`Contraindications (${response.contraindications.length})`);
  if (response.contraindications.length === 0) {
    drawText("No contraindications detected.", { color: "muted" });
  } else {
    for (const c of response.contraindications) {
      drawText(`• ${c.drug} vs ${c.condition}`, { bold: true });
      drawText(`  ${c.reasoning}`);
    }
  }

  // Risk breakdown
  drawSectionHeading("Risk Breakdown");
  drawText(`Interaction Risk: ${Math.round(response.risk_breakdown.interaction_risk)} / 100`);
  drawText(`Allergy Risk: ${Math.round(response.risk_breakdown.allergy_risk)} / 100`);
  drawText(`Contraindication Risk: ${Math.round(response.risk_breakdown.contraindication_risk)} / 100`);

  // Warnings
  drawSectionHeading(`Warnings (${response.warnings.length})`);
  if (response.warnings.length === 0) {
    drawText("No additional warnings.", { color: "muted" });
  } else {
    for (const w of response.warnings) {
      drawText(`• [${w.category.toUpperCase()}] ${w.message}`);
    }
  }

  // System info
  drawSectionHeading("System Info");
  drawText(`Source: ${response.system_info.source}    Cache Hit: ${response.system_info.cache_hit ? "true" : "false"}    Processing Time: ${response.system_info.processing_time_ms} ms`, { color: "muted", size: 8.5 });

  // Footer disclaimer
  ensureSpace(14);
  y += 4;
  setFill("muted");
  doc.rect(MARGIN, y, pageW - MARGIN * 2, 12, "F");
  setColor("muted");
  doc.setFont("helvetica", "italic");
  doc.setFontSize(8);
  const disclaimer =
    "DISCLAIMER: This report is generated by a Clinical Decision Support System and is intended " +
    "to assist — not replace — qualified clinical judgement. Always verify with current prescribing information.";
  const dl = doc.splitTextToSize(disclaimer, pageW - MARGIN * 2 - 4);
  doc.text(dl, MARGIN + 2, y + 4);

  doc.save(`drug-safety-report-${entry.id}.pdf`);
}

export type { SafetyCheckResponse };
