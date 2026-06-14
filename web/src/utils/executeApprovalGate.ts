import type { PlanExecutionRecord } from "../api/client";

export type ExecuteApprovalGate = {
  blocked: boolean;
  reason: string | null;
  pdfPath: string | null;
  pageCount: number | null;
  artifactsOk: boolean;
};

export function executionApprovalGate(
  pending: PlanExecutionRecord | null | undefined,
): ExecuteApprovalGate {
  const empty: ExecuteApprovalGate = {
    blocked: false,
    reason: null,
    pdfPath: null,
    pageCount: null,
    artifactsOk: true,
  };
  if (!pending?.needs_artifact_review) return empty;

  const arts = pending.verification_artifacts;
  const pdfPath =
    arts?.pdf_path ??
    pending.artifact_touched_paths?.find((p) =>
      p.toLowerCase().endsWith(".pdf"),
    ) ??
    pending.verification_paths?.find((p) => p.toLowerCase().endsWith(".pdf")) ??
    null;
  const pageCount =
    arts?.pdf_page_count ??
    (arts?.break_report as { baselinePdfPageCount?: number } | undefined)
      ?.baselinePdfPageCount ??
    null;
  const artifactsOk = Boolean(arts?.ok);

  if (!pdfPath && !arts?.break_report) {
    return {
      blocked: true,
      reason: "PDF 경로 또는 break-report.json 확인 후 승인하세요.",
      pdfPath,
      pageCount,
      artifactsOk,
    };
  }
  if (pageCount == null) {
    return {
      blocked: true,
      reason: "PDF 페이지 수 확인 후 승인하세요.",
      pdfPath,
      pageCount,
      artifactsOk,
    };
  }
  if (!artifactsOk) {
    return {
      blocked: true,
      reason:
        "검증 산출물이 불완전합니다 — PDF·break-report 확인 후 승인하세요.",
      pdfPath,
      pageCount,
      artifactsOk,
    };
  }

  return {
    blocked: false,
    reason: null,
    pdfPath,
    pageCount,
    artifactsOk: true,
  };
}
