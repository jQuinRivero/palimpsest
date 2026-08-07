"use client";

/**
 * One manuscript's card: the drop zone, the paste box, and everything the
 * uploader has to say about that witness.
 *
 * Extracted from ManuscriptUploader together with SlotDetails, which is only
 * ever rendered from here.
 */
import { EmptyState } from "./EmptyState";
import { formatBytes } from "./uploadFormats";
import { slotStatus, type SlotKey, type WitnessSlot } from "./witnessSlot";
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

export function WitnessCard({
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
        data-testid={`dropzone-${slotKey}`}
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
            message="Choose a witness in any format this server advertises, or paste plain text below."
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
