import type { Token, TokenStatus } from "@/lib/types";

const TONE: Record<TokenStatus, string> = {
  // Insertions surface. Deletions recede and show through — the palimpsest
  // metaphor. Underlays are tints, never the full-bleed blocks of a code diff:
  // at prose density those strobe and make sustained reading impossible.
  UNCHANGED: "",
  INSERTION:
    "bg-addition-underlay text-addition decoration-addition/50 underline decoration-1 underline-offset-4",
  DELETION:
    "bg-deletion-underlay text-deletion line-through decoration-deletion/60 decoration-1",
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

export function TokenSpan({ token }: { token: Token }) {
  const status = token.status as TokenStatus;

  if (status === "UNCHANGED") {
    return <span>{token.text}</span>;
  }

  const label = LABEL[status];

  return (
    <span className={TONE[status]} data-testid={`token-${status}`}>
      <span className="sr-only"> {label} text begins </span>
      {token.text}
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
