/**
 * Domain types for the palimpsest client.
 *
 * These are aliases onto the generated OpenAPI schema in `api-types.ts`, so
 * they cannot drift from the backend: if a Pydantic model changes, the
 * generated file changes and these aliases fail to compile.
 *
 * Field names are `snake_case` because the wire format is `snake_case` with no
 * aliasing — see docs/05-data-schema.md. That is deliberate.
 */
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type TokenStatus = Schemas["TokenStatus"];
export type BlockStatus = Schemas["BlockStatus"];
export type BlockKind = Schemas["BlockKind"];
export type SourceFormat = Schemas["SourceFormat"];
export type Granularity = Schemas["Granularity"];

export type Token = Schemas["Token"];
export type BlockMetrics = Schemas["BlockMetrics"];
export type DiffBlock = Schemas["DiffBlock"];
export type DiffMetrics = Schemas["DiffMetrics"];
export type DiffOptions = Schemas["DiffOptions"];
export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentMetadata = Schemas["DocumentMetadata"];
export type IngestionWarning = Schemas["IngestionWarning"];
export type ComparisonResult = Schemas["ComparisonResult"];
export type ComparisonAccepted = Schemas["ComparisonAccepted"];
export type BlockPage = Schemas["BlockPage"];
export type CapabilitiesResponse = Schemas["CapabilitiesResponse"];
export type ParserCapabilities = Schemas["ParserCapabilitiesResponse"];
export type ProblemDetail = Schemas["ProblemDetail"];
export type ErrorCode = Schemas["ErrorCode"];

/**
 * The side-by-side and single-column reading modes.
 *
 * Client-only: the server has no opinion about how a comparison is read.
 * Always "Manuscript A" and "Manuscript B", never "left" and "right" — the
 * panes swap under right-to-left scripts and collapse entirely in unified view.
 */
export type ViewMode = "synoptic" | "unified";
