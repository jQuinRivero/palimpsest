import type { Token, TokenStatus } from "@/lib/types";

const TONE: Record<TokenStatus, string> = {
  // Insertions surface. Deletions recede and show through — the palimpsest
  // metaphor. Underlays are tints, never the full-bleed blocks of a code diff:
  // at prose density those strobe and make sustained reading impossible.
  UNCHANGED: "",
  INSERTION:
    "box-decoration-clone rounded-sm bg-addition-underlay px-1 font-medium text-addition",
  DELETION:
    "box-decoration-clone rounded-sm bg-deletion-underlay px-1 text-deletion",
};

const DECORATION: Record<Exclude<TokenStatus, "UNCHANGED">, string> = {
  INSERTION: "underline decoration-addition decoration-2 underline-offset-4",
  DELETION: "line-through decoration-deletion decoration-2",
};

/**
 * Colour is never the only signal. Roughly one man in twelve has a colour
 * vision deficiency and this is a reading tool, so each status also carries a
 * text decoration and a screen-reader label.
 */
const LABEL: Record<TokenStatus, string | null> = {
  UNCHANGED: null,
  INSERTION: "inserted",
  DELETION: "deleted",
};

const SIGN: Record<Exclude<TokenStatus, "UNCHANGED">, string> = {
  INSERTION: "+",
  DELETION: "\u2212",
};

export function TokenSpan({ token }: { token: Token }) {
  const status = token.status as TokenStatus;

  if (status === "UNCHANGED") {
    return <span>{token.text}</span>;
  }

  const label = LABEL[status];

  return (
    <span
      className={TONE[status]}
      data-testid={`token-${status}`}
      data-token-status={status}
    >
      <span className="sr-only"> {label} text begins </span>
      <span
        aria-hidden="true"
        className="mr-0.5 select-none font-mono text-[0.75em] font-bold no-underline"
        data-testid={`token-sign-${status}`}
      >
        {SIGN[status]}
      </span>
      <span className={DECORATION[status]}>{token.text}</span>
      <span className="sr-only"> {label} text ends </span>
    </span>
  );
}

export function TokenStream({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((token, index) => (
        <TokenSpan key={index} token={token} />
      ))}
    </>
  );
}
