/**
 * What this server accepts, and how to say it to a person.
 *
 * The `accept` attribute and the prose sentence are deliberately different
 * renderings of the same capabilities response: the first is a comma-joined
 * list the file picker requires, the second is a sentence a researcher reads.
 */
import type { CapabilitiesResponse } from "../lib/types";
export function formatBytes(bytes: number) {
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

export function extensionOf(fileName: string) {
  const dot = fileName.lastIndexOf(".");
  return dot >= 0 ? fileName.slice(dot).toLowerCase() : "";
}

export function normalizeExtension(extension: string) {
  const clean = extension.trim().toLowerCase();
  return clean.startsWith(".") ? clean : `.${clean}`;
}

export function buildAccept(capabilities: CapabilitiesResponse | null) {
  if (!capabilities) return "";
  const values = new Set<string>();
  for (const parser of capabilities.parsers) {
    parser.extensions.forEach((extension) => values.add(normalizeExtension(extension)));
    parser.media_types.forEach((mediaType) => values.add(mediaType));
  }
  return Array.from(values).join(",");
}

/** How a format is named to a person, keyed by the server's own enum. */
const FORMAT_LABELS: Record<string, string> = {
  TXT: "plain text",
  MARKDOWN: "Markdown",
  DOCX: "Word documents",
  PDF: "PDF",
  OCR: "scanned pages",
};

/**
 * The accepted formats, written for a reader.
 *
 * Deliberately not the `accept` attribute. That value has to be a comma-joined
 * list of extensions and media types because the file picker requires it, and
 * putting it in a sentence produced this, unbroken and unspaced:
 *
 *     This server accepts .txt,text/plain,.markdown,.md,text/markdown,
 *     text/x-markdown,.docx,application/vnd.openxmlformats-officedocument.
 *     wordprocessingml.document,.pdf,application/pdf up to 25 MB.
 *
 * That was the first sentence a researcher read. Still derived from the
 * server's capabilities rather than hardcoded — a format nobody has a label
 * for falls back to its extensions, so registering the OCR parser needs no
 * change here.
 */
export function describeFormats(capabilities: CapabilitiesResponse | null): string {
  if (!capabilities) return "";

  const seen = new Set<string>();
  const names: string[] = [];
  for (const parser of capabilities.parsers) {
    const label =
      FORMAT_LABELS[parser.source_format] ??
      parser.extensions.map(normalizeExtension).join(" or ");
    if (label && !seen.has(label)) {
      seen.add(label);
      names.push(label);
    }
  }

  if (names.length === 0) return "";
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function isAcceptedFile(file: File, capabilities: CapabilitiesResponse) {
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

