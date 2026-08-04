"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createComparison, getCapabilities, uploadDocument } from "../lib/api";
import type {
  CapabilitiesResponse,
  ComparisonResult,
  DiffOptions,
  DocumentSummary,
  ErrorCode,
  IngestionWarning,
} from "../lib/types";
import { EmptyState } from "./EmptyState";

export interface ManuscriptUploaderProps {
  initialOptions?: Partial<DiffOptions>;
  onComparisonCreated?: (comparison: ComparisonResult) => void;
  onAccepted?: (accepted: ComparisonAccepted) => void;
  onError?: (problem: ApiProblem) => void;
}

type SlotKey = "a" | "b";
type SlotState = "empty" | "selected" | "uploading" | "uploaded" | "error";
type SlotLabel = "Manuscript A" | "Manuscript B";

interface ComparisonAccepted {
  comparison_id?: string;
}

interface ApiProblem {
  title: string;
  detail: string;
  code: ErrorCode | "UNKNOWN";
  status?: number;
}

interface WitnessSlot {
  label: SlotLabel;
  state: SlotState;
  file?: File;
  document?: DocumentSummary;
  warnings: IngestionWarning[];
  progress: number;
  error?: ApiProblem;
}

const defaultOptions: DiffOptions = {
  granularity: "WORD",
  detect_moves: true,
  align_threshold: 0.5,
  move_threshold: 0.75,
  ignore_case: false,
  ignore_punctuation: false,
  normalize_whitespace: true,
};

const emptySlots: Record<SlotKey, WitnessSlot> = {
  a: { label: "Manuscript A", state: "empty", warnings: [], progress: 0 },
  b: { label: "Manuscript B", state: "empty", warnings: [], progress: 0 },
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = units.shift() ?? "KB";
  while (value >= 1024 && units.length > 0) {
    value /= 1024;
    unit = units.shift() ?? unit;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unit}`;
}

function extensionOf(fileName: string) {
  const dot = fileName.lastIndexOf(".");
  return dot >= 0 ? fileName.slice(dot).toLowerCase() : "";
}

function normalizeExtension(extension: string) {
  const clean = extension.trim().toLowerCase();
  return clean.startsWith(".") ? clean : `.${clean}`;
}

function buildAccept(capabilities: CapabilitiesResponse | null) {
  if (!capabilities) return "";
  const values = new Set<string>();
  for (const parser of capabilities.parsers) {
    parser.extensions.forEach((extension) => values.add(normalizeExtension(extension)));
    parser.media_types.forEach((mediaType) => values.add(mediaType));
  }
  return Array.from(values).join(",");
}

function isAcceptedFile(file: File, capabilities: CapabilitiesResponse) {
  const extensions = new Set(
    capabilities.parsers.flatMap((parser) => parser.extensions.map(normalizeExtension)),
  );
  const mediaTypes = new Set(
    capabilities.parsers.flatMap((parser) =>
      parser.media_types.map((mediaType) => mediaType.toLowerCase()),
    ),
  );
  const extension = extensionOf(file.name);
  const mediaType = file.type.toLowerCase();
  return (extension && extensions.has(extension)) || (mediaType && mediaTypes.has(mediaType));
}

function problemFromApiError(error: ApiError): ApiProblem {
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

function titleForCode(code: ErrorCode | "UNKNOWN") {
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

function problemFromUnknown(error: unknown): ApiProblem {
  if (error instanceof ApiError) return problemFromApiError(error);
  return {
    title: "Request failed",
    detail: error instanceof Error ? error.message : "An unexpected error occurred.",
    code: "UNKNOWN",
  };
}

function localProblem(code: ErrorCode, detail: string): ApiProblem {
  return { title: titleForCode(code), detail, code };
}

function slotStatus(slot: WitnessSlot) {
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
      return `${slot.label} has an error: ${slot.error?.detail ?? "Upload failed."}`;
  }
}

export function ManuscriptUploader({
  initialOptions,
  onComparisonCreated,
  onAccepted,
  onError,
}: ManuscriptUploaderProps) {
  const router = useRouter();
  const inputRefs = {
    a: useRef<HTMLInputElement>(null),
    b: useRef<HTMLInputElement>(null),
  };
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [capabilitiesProblem, setCapabilitiesProblem] = useState<ApiProblem | null>(null);
  const [slots, setSlots] = useState<Record<SlotKey, WitnessSlot>>(emptySlots);
  const [pasteDrafts, setPasteDrafts] = useState<Record<SlotKey, string>>({ a: "", b: "" });
  const [isDragging, setIsDragging] = useState<Record<SlotKey, boolean>>({ a: false, b: false });
  const [submissionProblem, setSubmissionProblem] = useState<ApiProblem | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const accept = useMemo(() => buildAccept(capabilities), [capabilities]);
  const options = useMemo(
    () => ({ ...capabilities?.diff_options_defaults, ...defaultOptions, ...initialOptions }),
    [capabilities, initialOptions],
  );

  void onAccepted;

  useEffect(() => {
    let isMounted = true;
    getCapabilities()
      .then((response) => {
        if (isMounted) setCapabilities(response);
      })
      .catch((error: unknown) => {
        const problem = problemFromUnknown(error);
        if (isMounted) {
          setCapabilitiesProblem(problem);
          onError?.(problem);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [onError]);

  async function selectFile(key: SlotKey, file: File) {
    setSubmissionProblem(null);

    if (!capabilities) {
      setSlotError(key, localProblem("UNSUPPORTED_FORMAT", "Accepted formats are still loading."));
      return;
    }

    if (file.size > capabilities.max_upload_bytes) {
      setSlots((current) => ({
        ...current,
        [key]: {
          ...current[key],
          state: "error",
          file,
          document: undefined,
          warnings: [],
          progress: 0,
          error: localProblem(
            "FILE_TOO_LARGE",
            `${file.name} is ${formatBytes(file.size)}. The upload limit is ${formatBytes(
              capabilities.max_upload_bytes,
            )}.`,
          ),
        },
      }));
      return;
    }

    if (!isAcceptedFile(file, capabilities)) {
      setSlots((current) => ({
        ...current,
        [key]: {
          ...current[key],
          state: "error",
          file,
          document: undefined,
          warnings: [],
          progress: 0,
          error: localProblem(
            "UNSUPPORTED_FORMAT",
            `${file.name} is not one of the formats advertised by this server.`,
          ),
        },
      }));
      return;
    }

    setSlots((current) => ({
      ...current,
      [key]: {
        ...current[key],
        state: "selected",
        file,
        document: undefined,
        warnings: [],
        progress: 0,
        error: undefined,
      },
    }));

    setSlots((current) => ({
      ...current,
      [key]: { ...current[key], state: "uploading", progress: 20 },
    }));

    try {
      const document = await uploadDocument(file, file.name);
      setSlots((current) => ({
        ...current,
        [key]: {
          ...current[key],
          state: "uploaded",
          document,
          warnings: document.warnings ?? [],
          progress: 100,
          error: undefined,
        },
      }));
    } catch (error: unknown) {
      const problem = problemFromUnknown(error);
      setSlots((current) => ({
        ...current,
        [key]: {
          ...current[key],
          state: "error",
          warnings: [],
          progress: 0,
          error: problem,
        },
      }));
      onError?.(problem);
    }
  }

  function setSlotError(key: SlotKey, problem: ApiProblem) {
    setSlots((current) => ({
      ...current,
      [key]: { ...current[key], state: "error", error: problem, progress: 0 },
    }));
    onError?.(problem);
  }

  function resetSlot(key: SlotKey) {
    setSlots((current) => ({
      ...current,
      [key]: { label: current[key].label, state: "empty", warnings: [], progress: 0 },
    }));
    setPasteDrafts((current) => ({ ...current, [key]: "" }));
  }

  function swapSlots() {
    setSlots((current) => ({
      a: { ...current.b, label: "Manuscript A" },
      b: { ...current.a, label: "Manuscript B" },
    }));
    setPasteDrafts((current) => ({ a: current.b, b: current.a }));
    setSubmissionProblem(null);
  }

  async function pasteAsFile(key: SlotKey) {
    const text = pasteDrafts[key].trim();
    if (!text) {
      setSlotError(key, localProblem("EMPTY_DOCUMENT", "Paste some text before uploading."));
      return;
    }
    await selectFile(key, new File([text], "pasted.txt", { type: "text/plain" }));
  }

  async function submitComparison() {
    if (!slots.a.document || !slots.b.document) return;
    setIsSubmitting(true);
    setSubmissionProblem(null);
    try {
      const comparison = await createComparison(slots.a.document.id, slots.b.document.id, options);
      onComparisonCreated?.(comparison);
      router.push(`/c/${comparison.comparison_id}`);
    } catch (error: unknown) {
      const problem = problemFromUnknown(error);
      setSubmissionProblem(problem);
      onError?.(problem);
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit = slots.a.state === "uploaded" && slots.b.state === "uploaded" && !isSubmitting;

  return (
    <section
      data-testid="manuscript-uploader"
      className="font-ui text-ink"
      aria-labelledby="uploader-heading"
    >
      <div className="mx-auto max-w-5xl">
        <div className="mb-10 max-w-3xl">
          <p className="text-sm uppercase tracking-[0.24em] text-rubric">new comparison</p>
          <h1 id="uploader-heading" className="mt-3 font-manuscript text-5xl text-ink">
            palimpsest
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-muted">
            Upload two witnesses and read how Manuscript A becomes Manuscript B.
          </p>
        </div>

        <div className="mb-6 rounded-2xl border border-rule bg-vellum/35 p-4 text-sm text-ink-muted">
          {capabilities ? (
            <p>
              This server accepts {accept || "the advertised parser formats"} up to{" "}
              {formatBytes(capabilities.max_upload_bytes)}.
            </p>
          ) : capabilitiesProblem ? (
            <p role="status">
              Could not load parser capabilities: {capabilitiesProblem.detail}
            </p>
          ) : (
            <p role="status">Loading accepted formats from the server…</p>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-start">
          <WitnessCard
            slotKey="a"
            slot={slots.a}
            accept={accept}
            capabilitiesReady={Boolean(capabilities)}
            inputRef={inputRefs.a}
            isDragging={isDragging.a}
            pasteDraft={pasteDrafts.a}
            onBrowse={() => inputRefs.a.current?.click()}
            onFile={(file) => void selectFile("a", file)}
            onPasteDraft={(text) => setPasteDrafts((current) => ({ ...current, a: text }))}
            onPasteUpload={() => void pasteAsFile("a")}
            onReset={() => resetSlot("a")}
            onDragState={(dragging) => setIsDragging((current) => ({ ...current, a: dragging }))}
          />

          <div className="flex justify-center lg:pt-32">
            <button
              type="button"
              onClick={swapSlots}
              className="rounded-full border border-rule bg-paper px-5 py-3 text-sm font-medium text-rubric shadow-sm outline-none transition hover:border-rubric focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
              aria-label="Swap Manuscript A and Manuscript B"
            >
              Swap A ↔ B
            </button>
          </div>

          <WitnessCard
            slotKey="b"
            slot={slots.b}
            accept={accept}
            capabilitiesReady={Boolean(capabilities)}
            inputRef={inputRefs.b}
            isDragging={isDragging.b}
            pasteDraft={pasteDrafts.b}
            onBrowse={() => inputRefs.b.current?.click()}
            onFile={(file) => void selectFile("b", file)}
            onPasteDraft={(text) => setPasteDrafts((current) => ({ ...current, b: text }))}
            onPasteUpload={() => void pasteAsFile("b")}
            onReset={() => resetSlot("b")}
            onDragState={(dragging) => setIsDragging((current) => ({ ...current, b: dragging }))}
          />
        </div>

        <div className="mt-8 rounded-2xl border border-rule bg-vellum/50 p-5">
          {submissionProblem ? (
            <div
              id="comparison-error"
              role="status"
              aria-live="polite"
              className="mb-4 rounded-xl border border-deletion bg-deletion-underlay/40 p-4 text-sm text-ink"
            >
              <p className="font-medium">{submissionProblem.title}</p>
              <p className="mt-1">{submissionProblem.detail}</p>
              <p className="mt-2 font-mono text-xs text-ink-muted">Code: {submissionProblem.code}</p>
            </div>
          ) : null}

          <button
            type="button"
            onClick={() => void submitComparison()}
            disabled={!canSubmit}
            aria-describedby={submissionProblem ? "comparison-error" : undefined}
            className="w-full rounded-full border border-rubric bg-rubric px-6 py-4 text-base font-semibold text-paper outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:border-rule disabled:bg-rule disabled:text-ink-muted"
          >
            {isSubmitting ? "Preparing comparison…" : "Compare Manuscript A and Manuscript B"}
          </button>
        </div>
      </div>
    </section>
  );
}

interface WitnessCardProps {
  slotKey: SlotKey;
  slot: WitnessSlot;
  accept: string;
  capabilitiesReady: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  isDragging: boolean;
  pasteDraft: string;
  onBrowse: () => void;
  onFile: (file: File) => void;
  onPasteDraft: (text: string) => void;
  onPasteUpload: () => void;
  onReset: () => void;
  onDragState: (dragging: boolean) => void;
}

function WitnessCard({
  slotKey,
  slot,
  accept,
  capabilitiesReady,
  inputRef,
  isDragging,
  pasteDraft,
  onBrowse,
  onFile,
  onPasteDraft,
  onPasteUpload,
  onReset,
  onDragState,
}: WitnessCardProps) {
  const inputId = `${slotKey}-file`;
  const errorId = `${slotKey}-error`;
  const warningId = `${slotKey}-warnings`;
  const descriptionId = `${slotKey}-description`;
  const describedBy = [
    descriptionId,
    slot.error ? errorId : null,
    slot.warnings.length > 0 ? warningId : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className="rounded-3xl border border-rule bg-paper p-5 shadow-sm">
      <div className="mb-4">
        <label htmlFor={inputId} className="font-manuscript text-3xl text-ink">
          {slot.label}
        </label>
        <p id={descriptionId} className="mt-2 text-sm leading-6 text-ink-muted">
          Drop a file, browse, or paste text for this witness.
        </p>
      </div>

      <div
        onDragEnter={(event) => {
          event.preventDefault();
          if (capabilitiesReady && slot.state !== "uploading") onDragState(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => onDragState(false)}
        onDrop={(event) => {
          event.preventDefault();
          onDragState(false);
          const file = event.dataTransfer.files.item(0);
          if (file) onFile(file);
        }}
        className={`rounded-2xl border p-4 transition ${
          isDragging
            ? "border-rubric bg-vellum"
            : slot.state === "error"
              ? "border-deletion bg-deletion-underlay/30"
              : "border-rule bg-vellum/45"
        }`}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={accept}
          disabled={!capabilitiesReady || slot.state === "uploading"}
          className="sr-only"
          aria-describedby={describedBy}
          onChange={(event) => {
            const file = event.target.files?.item(0);
            if (file) onFile(file);
            event.currentTarget.value = "";
          }}
        />

        {slot.state === "empty" ? (
          <EmptyState
            title={`Add ${slot.label}`}
            message="Choose a text, Markdown, Word, or PDF witness from the formats this server advertises, or paste plain text below."
            actionLabel={`Browse for ${slot.label}`}
            onAction={onBrowse}
          />
        ) : (
          <SlotDetails slot={slot} errorId={errorId} warningId={warningId} onReset={onReset} />
        )}

        {slot.state !== "empty" ? (
          <button
            type="button"
            onClick={onBrowse}
            disabled={!capabilitiesReady || slot.state === "uploading"}
            className="mt-4 rounded-full border border-rule px-4 py-2 text-sm font-medium text-rubric outline-none hover:border-rubric focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:text-ink-muted"
          >
            Replace {slot.label}
          </button>
        ) : null}
      </div>

      <div className="mt-5">
        <label htmlFor={`${slotKey}-paste`} className="text-sm font-medium text-ink">
          Paste text for {slot.label}
        </label>
        <textarea
          id={`${slotKey}-paste`}
          value={pasteDraft}
          onChange={(event) => onPasteDraft(event.target.value)}
          disabled={!capabilitiesReady || slot.state === "uploading"}
          rows={5}
          className="mt-2 w-full rounded-2xl border border-rule bg-paper p-3 font-manuscript text-base leading-7 text-ink outline-none focus-visible:ring-2 focus-visible:ring-rubric disabled:cursor-not-allowed disabled:text-ink-muted"
          placeholder="Paste witness text…"
        />
        <button
          type="button"
          onClick={onPasteUpload}
          disabled={!capabilitiesReady || slot.state === "uploading" || pasteDraft.trim().length === 0}
          className="mt-3 rounded-full border border-rule px-4 py-2 text-sm font-medium text-rubric outline-none hover:border-rubric focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:text-ink-muted"
        >
          Upload pasted text
        </button>
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {slotStatus(slot)}
      </p>
    </article>
  );
}

function SlotDetails({
  slot,
  errorId,
  warningId,
  onReset,
}: {
  slot: WitnessSlot;
  errorId: string;
  warningId: string;
  onReset: () => void;
}) {
  return (
    <div>
      <div className="rounded-xl bg-paper/70 p-4">
        <p className="text-sm uppercase tracking-[0.18em] text-ink-muted">{slot.state}</p>
        {slot.file ? (
          <>
            <p className="mt-2 font-medium text-ink">{slot.file.name}</p>
            <p className="mt-1 text-sm text-ink-muted">
              {formatBytes(slot.file.size)}
              {slot.file.type ? ` · ${slot.file.type}` : ""}
            </p>
          </>
        ) : null}
      </div>

      {slot.state === "uploading" ? (
        <div className="mt-4">
          <div
            role="progressbar"
            aria-valuenow={slot.progress}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-2 overflow-hidden rounded-full bg-rule"
          >
            <div className="h-full bg-rubric" style={{ width: `${slot.progress}%` }} />
          </div>
          <p className="mt-2 text-sm text-ink-muted">Uploading…</p>
        </div>
      ) : null}

      {slot.document ? (
        <div className="mt-4 rounded-xl border border-rule bg-vellum/50 p-4">
          <p className="font-medium text-ink">{slot.document.title}</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-ink-muted">Words</dt>
              <dd className="font-mono text-ink">{slot.document.metadata.word_count}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Blocks</dt>
              <dd className="font-mono text-ink">{slot.document.metadata.block_count}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-ink-muted">Parser</dt>
              <dd className="font-mono text-ink">
                {slot.document.metadata.parser_name} {slot.document.metadata.parser_version}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}

      {slot.warnings.length > 0 ? (
        <div id={warningId} className="mt-4 rounded-xl border border-rule bg-vellum/60 p-4">
          <p className="font-medium text-ink">Parser warnings</p>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-ink-muted">
            {slot.warnings.map((warning, index) => (
              <li key={`${warning.code}-${warning.block_id ?? index}`}>
                <span className="font-mono text-xs">{warning.code}</span>: {warning.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {slot.error ? (
        <div
          id={errorId}
          role="status"
          aria-live="polite"
          className="mt-4 rounded-xl border border-deletion bg-deletion-underlay/40 p-4 text-sm text-ink"
        >
          <p className="font-medium">{slot.error.title}</p>
          <p className="mt-1">{slot.error.detail}</p>
          <p className="mt-2 font-mono text-xs text-ink-muted">Code: {slot.error.code}</p>
          <button
            type="button"
            onClick={onReset}
            className="mt-3 rounded-full border border-rule px-3 py-1.5 text-sm font-medium text-rubric outline-none hover:border-rubric focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
          >
            Clear and try again
          </button>
        </div>
      ) : null}
    </div>
  );
}
