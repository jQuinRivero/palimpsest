/**
 * Turning a failure into something a researcher can act on.
 *
 * Every refusal reaches the reader through here, whether it came from the
 * server or from the local pre-check, so the two are worded from one place.
 */
import { ApiError } from "../lib/api";
import type { ErrorCode } from "../lib/types";
import type { ApiProblem } from "./witnessSlot";
export function problemFromApiError(error: ApiError): ApiProblem {
  if (error.code === "OCR_REQUIRED") {
    return {
      title: "OCR required",
      detail:
        "This witness appears to require OCR before it can be compared. Export searchable text, upload a text-based PDF, or enable the OCR parser when it becomes available.",
      code: error.code,
      status: error.status,
    };
  }
  return {
    title: error.problem?.title ?? titleForCode(error.code),
    detail: error.message,
    code: error.code,
    status: error.status,
  };
}

export function titleForCode(code: ErrorCode | "UNKNOWN") {
  switch (code) {
    case "UNSUPPORTED_FORMAT":
      return "Unsupported format";
    case "FILE_TOO_LARGE":
      return "File too large";
    case "EMPTY_DOCUMENT":
      return "Empty document";
    case "MALFORMED_DOCUMENT":
      return "Malformed document";
    case "OCR_REQUIRED":
      return "OCR required";
    default:
      return "Upload failed";
  }
}

export function problemFromUnknown(error: unknown): ApiProblem {
  if (error instanceof ApiError) return problemFromApiError(error);
  return {
    title: "Request failed",
    detail: error instanceof Error ? error.message : "An unexpected error occurred.",
    code: "UNKNOWN",
  };
}

export function localProblem(code: ErrorCode, detail: string): ApiProblem {
  return { title: titleForCode(code), detail, code };
}

