"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { createComparison, getCapabilities, uploadDocument } from "../lib/api";
import { waitForComparison, type PollProgress } from "../lib/waitForComparison";
import type {
  CapabilitiesResponse,
  ComparisonAccepted,
  ComparisonResult,
  DiffOptions,
} from "../lib/types";
import { WitnessCard } from "./WitnessCard";
import { buildAccept, describeFormats, formatBytes, isAcceptedFile } from "./uploadFormats";
import { localProblem, problemFromUnknown } from "./uploadProblems";
import { emptySlots, type ApiProblem, type SlotKey, type WitnessSlot } from "./witnessSlot";

// Re-exported because the split below is an internal reorganisation. Nothing
// that imports the uploader should have to learn a new module to keep naming
// the same things.
export type { ApiProblem, SlotKey, WitnessSlot } from "./witnessSlot";

export interface ManuscriptUploaderProps {
  initialOptions?: Partial<DiffOptions>;
  onComparisonCreated?: (comparison: ComparisonResult) => void;
  onAccepted?: (accepted: ComparisonAccepted) => void;
  onError?: (problem: ApiProblem) => void;
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


export function ManuscriptUploader({
  initialOptions,
  onComparisonCreated,
  onAccepted,
  onError,
}: ManuscriptUploaderProps) {
  const router = useRouter();
  const inputRefA = useRef<HTMLInputElement>(null);
  const inputRefB = useRef<HTMLInputElement>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [capabilitiesProblem, setCapabilitiesProblem] = useState<ApiProblem | null>(null);
  const [slots, setSlots] = useState<Record<SlotKey, WitnessSlot>>(emptySlots);
  const [pasteDrafts, setPasteDrafts] = useState<Record<SlotKey, string>>({ a: "", b: "" });
  const [isDragging, setIsDragging] = useState<Record<SlotKey, boolean>>({ a: false, b: false });
  const [submissionProblem, setSubmissionProblem] = useState<ApiProblem | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [collating, setCollating] = useState<PollProgress | null>(null);
  const accept = useMemo(() => buildAccept(capabilities), [capabilities]);
  const formatSummary = useMemo(() => describeFormats(capabilities), [capabilities]);
  const options = useMemo(
    () => ({ ...capabilities?.diff_options_defaults, ...defaultOptions, ...initialOptions }),
    [capabilities, initialOptions],
  );

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

    // The checks below are a courtesy: they fail fast and locally so a
    // researcher is not made to wait for an upload that cannot succeed. The
    // server is the authority on both format and size and re-checks each.
    //
    // So when capabilities have not arrived, the honest move is to upload and
    // let the server answer. Refusing here instead told the researcher their
    // file was an UNSUPPORTED_FORMAT — which is not something we know yet, and
    // may well be false — and then discarded it, so a slow capabilities
    // request turned a perfectly good manuscript into a dead end they had to
    // select again.
    if (capabilities && file.size > capabilities.max_upload_bytes) {
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
            `This file is ${formatBytes(file.size)}. The upload limit is ${formatBytes(
              capabilities.max_upload_bytes,
            )}.`,
          ),
        },
      }));
      return;
    }

    if (capabilities && !isAcceptedFile(file, capabilities)) {
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
            "This is not one of the formats advertised by this server.",
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
    setCollating(null);
    try {
      const outcome = await createComparison(
        slots.a.document.id,
        slots.b.document.id,
        options,
      );

      if (outcome.status === "COMPLETE") {
        onComparisonCreated?.(outcome.comparison);
        router.push(`/c/${outcome.comparison.comparison_id}`);
        return;
      }

      // Accepted, not finished. Wait here rather than navigating to a
      // comparison that does not exist yet.
      onAccepted?.(outcome.accepted);
      const { comparison_id: comparisonId, retry_after: retryAfter } = outcome.accepted;
      setCollating({ attempt: 0, elapsedMs: 0 });
      await waitForComparison(comparisonId, {
        initialDelayMs: retryAfter * 1000,
        onProgress: setCollating,
      });
      router.push(`/c/${comparisonId}`);
    } catch (error: unknown) {
      const problem = problemFromUnknown(error);
      setSubmissionProblem(problem);
      onError?.(problem);
    } finally {
      setIsSubmitting(false);
      setCollating(null);
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
            <p data-testid="accepted-formats">
              This server accepts {formatSummary || "the advertised parser formats"}, up to{" "}
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
            inputRef={inputRefA}
            isDragging={isDragging.a}
            pasteDraft={pasteDrafts.a}
            onBrowse={() => inputRefA.current?.click()}
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
            inputRef={inputRefB}
            isDragging={isDragging.b}
            pasteDraft={pasteDrafts.b}
            onBrowse={() => inputRefB.current?.click()}
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

          {collating ? (
            <p
              className="mt-4 text-center text-sm text-ink-muted"
              data-testid="collating-status"
              aria-live="polite"
            >
              {/* No estimate. The server does not know how long this will
                  take, so promising a number would be inventing one. */}
              Collating two long manuscripts. This can take a little while — the
              page will open the comparison as soon as it is ready.
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
