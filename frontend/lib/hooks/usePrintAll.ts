"use client";

import { useEffect, useState } from "react";
import { flushSync } from "react-dom";

/**
 * True while the browser is preparing a printed copy.
 *
 * Both reading surfaces are virtualized, so only the rows near the viewport
 * exist in the DOM. Printing in that state puts a fraction of the collation on
 * paper — measured at 42 of 300 blocks — with nothing on the page to say so.
 * That is the same failure as rendering a truncated comparison as a whole one,
 * except the artifact leaves the building.
 *
 * `flushSync` is what makes this work rather than merely intend to. React
 * batches state updates, and the browser snapshots the document as soon as the
 * `beforeprint` handler returns; an ordinary `setState` would land after the
 * snapshot and print exactly the fragment it was meant to prevent.
 */
export function usePrintAll(): boolean {
  const [printing, setPrinting] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const before = () => flushSync(() => setPrinting(true));
    const after = () => setPrinting(false);

    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);

    // Emulated print media fires no beforeprint event, so the media query is
    // watched as well. This is what makes the behaviour testable, and it also
    // covers browsers that switch media without announcing it.
    const media = window.matchMedia("print");
    const onMediaChange = (event: MediaQueryListEvent) => setPrinting(event.matches);
    media.addEventListener("change", onMediaChange);

    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
      media.removeEventListener("change", onMediaChange);
    };
  }, []);

  return printing;
}
