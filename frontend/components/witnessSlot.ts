/**
 * One witness slot: what the uploader knows about a manuscript, and how that
 * state is spoken aloud.
 *
 * Extracted from ManuscriptUploader, which had grown to 800 lines holding
 * three components and ten helpers.
 */
import type { DocumentSummary, ErrorCode, IngestionWarning } from "../lib/types";

export type SlotKey = "a" | "b";
export type SlotState = "empty" | "selected" | "uploading" | "uploaded" | "error";
export type SlotLabel = "Manuscript A" | "Manuscript B";
export interface ApiProblem {
  title: string;
  detail: string;
  code: ErrorCode | "UNKNOWN";
  status?: number;
}

export interface WitnessSlot {
  label: SlotLabel;
  state: SlotState;
  file?: File;
  document?: DocumentSummary;
  warnings: IngestionWarning[];
  progress: number;
  error?: ApiProblem;
}

export const emptySlots: Record<SlotKey, WitnessSlot> = {
  a: { label: "Manuscript A", state: "empty", warnings: [], progress: 0 },
  b: { label: "Manuscript B", state: "empty", warnings: [], progress: 0 },
};

export function slotStatus(slot: WitnessSlot) {
  switch (slot.state) {
    case "empty":
      return `${slot.label} is empty.`;
    case "selected":
      return `${slot.label} selected ${slot.file?.name ?? "a file"}.`;
    case "uploading":
      return `${slot.label} is uploading.`;
    case "uploaded":
      return `${slot.label} uploaded ${slot.document?.title ?? slot.file?.name ?? "a file"}.`;
    case "error":
      // The file is named here rather than left to the message. Whether a
      // refusal comes from the local pre-check or from the server is a race
      // once capabilities are slow, and the two word it differently — the
      // server's is deliberately about parsers, not about this upload. A
      // researcher comparing two witnesses needs to know which file failed
      // whichever authority answered, and a listener has only this sentence:
      // the card names the file on screen, but that is not read out here.
      return `${slot.label} has an error${
        slot.file ? ` with ${slot.file.name}` : ""
      }: ${slot.error?.detail ?? "Upload failed."}`;
  }
}
