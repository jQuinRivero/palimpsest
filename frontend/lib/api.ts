/**
 * Typed client for the palimpsest API.
 *
 * Errors arrive as RFC 9457 `application/problem+json`; they are surfaced as
 * `ApiError` carrying the machine-readable `code`, so callers branch on the
 * code rather than parsing prose.
 */
import type {
  BlockPage,
  CapabilitiesResponse,
  ComparisonAccepted,
  ComparisonResult,
  DiffOptions,
  DocumentSummary,
  ErrorCode,
  ProblemDetail,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly code: ErrorCode | "UNKNOWN";
  readonly status: number;
  readonly problem?: ProblemDetail;

  constructor(status: number, code: ErrorCode | "UNKNOWN", detail: string, problem?: ProblemDetail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.problem = problem;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const problem = (await response.json()) as ProblemDetail;
    return new ApiError(response.status, problem.code ?? "UNKNOWN", problem.detail, problem);
  } catch {
    return new ApiError(response.status, "UNKNOWN", response.statusText || "Request failed");
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    // Comparisons may contain unpublished material; never let an intermediary
    // hold on to one.
    cache: "no-store",
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

/**
 * A comparison is either finished or still being collated.
 *
 * The server answers `202` for a comparison above its inline budget and
 * computes it in the background. `202` is a success status, so a client that
 * only checks `response.ok` receives a `ComparisonAccepted` — which carries no
 * blocks and no metrics — while believing it holds a `ComparisonResult`. That
 * is how uploading two large manuscripts used to end at a 500 page reading
 * "Cannot read properties of undefined (reading 'length')".
 *
 * Making the two outcomes distinct types means the caller cannot skip the
 * question.
 */
export type ComparisonOutcome =
  | { status: "COMPLETE"; comparison: ComparisonResult }
  | { status: "PENDING"; accepted: ComparisonAccepted };

async function requestComparison(
  path: string,
  init?: RequestInit,
): Promise<ComparisonOutcome> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 202) {
    return { status: "PENDING", accepted: (await response.json()) as ComparisonAccepted };
  }
  return { status: "COMPLETE", comparison: (await response.json()) as ComparisonResult };
}

export function getCapabilities(): Promise<CapabilitiesResponse> {
  return request<CapabilitiesResponse>("/api/v1/capabilities");
}

export async function uploadDocument(
  file: File,
  title?: string,
): Promise<DocumentSummary> {
  const form = new FormData();
  form.append("file", file);
  if (title) {
    form.append("title", title);
  }
  return request<DocumentSummary>("/api/v1/documents", {
    method: "POST",
    body: form,
  });
}

export function createComparison(
  aDocumentId: string,
  bDocumentId: string,
  options?: Partial<DiffOptions>,
): Promise<ComparisonOutcome> {
  return requestComparison("/api/v1/comparisons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      a_document_id: aDocumentId,
      b_document_id: bDocumentId,
      ...(options ? { options } : {}),
    }),
  });
}

export function getComparison(
  comparisonId: string,
  includeBlocks = true,
): Promise<ComparisonOutcome> {
  const query = includeBlocks ? "" : "?include_blocks=false";
  return requestComparison(`/api/v1/comparisons/${comparisonId}${query}`);
}

export function getComparisonBlocks(
  comparisonId: string,
  offset: number,
  limit: number,
): Promise<BlockPage> {
  return request<BlockPage>(
    `/api/v1/comparisons/${comparisonId}/blocks?offset=${offset}&limit=${limit}`,
  );
}

/**
 * The TEI export is a URL rather than a fetch.
 *
 * The endpoint answers with `Content-Disposition: attachment`, so an ordinary
 * link downloads the file — no blob, no object URL to revoke, and it still
 * works with JavaScript disabled. Fetching it into memory would also mean
 * holding a whole manuscript's markup in the tab to hand it straight back.
 */
export function teiExportUrl(comparisonId: string): string {
  return `${API_BASE}/api/v1/comparisons/${encodeURIComponent(comparisonId)}/export/tei`;
}
