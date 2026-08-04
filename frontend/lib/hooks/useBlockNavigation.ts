"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import type { DiffBlock } from "@/lib/types";

const CHANGE_STATUSES = new Set<DiffBlock["status"]>([
  "MODIFIED",
  "INSERTED",
  "DELETED",
  "MOVED",
  "SPLIT",
  "MERGED",
]);

export interface BlockNavigationState {
  changedBlockIndices: number[];
  activeBlockIndex: number | null;
  activeChangedPosition: number | null;
  totalChanges: number;
  next: () => void;
  previous: () => void;
  goTo: (blockIndex: number) => void;
  clear: () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName.toLowerCase();
  return (
    tagName === "input" ||
    tagName === "textarea" ||
    tagName === "select" ||
    target.isContentEditable
  );
}

function escapeAttributeValue(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function findBlockElement(blocks: readonly DiffBlock[], blockIndex: number) {
  const documentedAnchor = document.getElementById(`block-${blockIndex}`);
  if (documentedAnchor instanceof HTMLElement) {
    return documentedAnchor;
  }

  const block = blocks[blockIndex];
  if (block?.id !== undefined) {
    const byTestId = document.querySelector<HTMLElement>(
      `[data-testid="diff-block-row-${escapeAttributeValue(String(block.id))}"]`,
    );
    if (byTestId) {
      return byTestId;
    }

    const currentSynopticAnchor =
      document.getElementById(`block-b-${block.id}`) ??
      document.getElementById(`block-unified-${block.id}`);
    if (currentSynopticAnchor instanceof HTMLElement) {
      return currentSynopticAnchor;
    }
  }

  return null;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function parseBlockParam(value: string | null, blockCount: number): number | null {
  if (value === null || !/^\d+$/.test(value)) {
    return null;
  }

  const index = Number(value);
  return Number.isSafeInteger(index) && index >= 0 && index < blockCount ? index : null;
}

function clampBlockIndex(index: number, blockCount: number): number | null {
  return Number.isSafeInteger(index) && index >= 0 && index < blockCount ? index : null;
}

export function useBlockNavigation(
  blocks: readonly DiffBlock[],
  initialBlockIndex?: number | null,
  totalBlocks?: number,
): BlockNavigationState {
  const pathname = usePathname();
  // Bounds for *intent* are the whole comparison; bounds for *rendering* are
  // what has loaded. A long comparison arrives in windows, so a shared link to
  // block 2500 is legitimate long before block 2500 exists on the client.
  const comparisonSize = Math.max(totalBlocks ?? blocks.length, blocks.length);
  const [activeBlockIndex, setActiveBlockIndex] = useState<number | null>(() => {
    // Seeded from the server so that the first render matches on both sides.
    // Reading window.location here instead would make the server render the
    // neutral label and the client render the active one, which React reports
    // as a hydration mismatch — and would mean a shared ?block= link paints
    // the wrong state before correcting itself.
    if (initialBlockIndex !== undefined && initialBlockIndex !== null) {
      return clampBlockIndex(initialBlockIndex, comparisonSize);
    }
    if (typeof window === "undefined") {
      return null;
    }

    return parseBlockParam(
      new URLSearchParams(window.location.search).get("block"),
      comparisonSize,
    );
  });
  const hasFocusedInitialBlock = useRef(false);
  const safeActiveBlockIndex =
    activeBlockIndex !== null && activeBlockIndex < blocks.length ? activeBlockIndex : null;

  const changedBlockIndices = useMemo(
    () =>
      blocks.reduce<number[]>((indices, block, index) => {
        if (CHANGE_STATUSES.has(block.status)) {
          indices.push(index);
        }
        return indices;
      }, []),
    [blocks],
  );

  const activeChangedPosition = useMemo(() => {
    if (safeActiveBlockIndex === null) {
      return null;
    }

    const position = changedBlockIndices.indexOf(safeActiveBlockIndex);
    return position === -1 ? null : position;
  }, [safeActiveBlockIndex, changedBlockIndices]);

  const replaceBlockParam = useCallback(
    (blockIndex: number | null) => {
      if (typeof window === "undefined") {
        return;
      }

      const params = new URLSearchParams(window.location.search);
      if (blockIndex === null) {
        params.delete("block");
      } else {
        params.set("block", String(blockIndex));
      }

      const query = params.toString();
      const nextUrl = query ? `${pathname}?${query}` : pathname;
      window.history.replaceState(null, "", nextUrl);
    },
    [pathname],
  );

  const focusBlock = useCallback((blockIndex: number) => {
    if (typeof window === "undefined") {
      return;
    }

    window.requestAnimationFrame(() => {
      const target = findBlockElement(blocks, blockIndex);
      if (!target) {
        return;
      }

      if (!target.hasAttribute("tabindex")) {
        target.setAttribute("tabindex", "-1");
      }

      target.focus({ preventScroll: true });
      target.scrollIntoView({
        block: "center",
        inline: "nearest",
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
    });
  }, [blocks]);

  const goTo = useCallback(
    (blockIndex: number) => {
      if (!Number.isSafeInteger(blockIndex) || blockIndex < 0 || blockIndex >= comparisonSize) {
        replaceBlockParam(null);
        setActiveBlockIndex(null);
        return;
      }

      setActiveBlockIndex(blockIndex);
      replaceBlockParam(blockIndex);
      focusBlock(blockIndex);
    },
    [comparisonSize, focusBlock, replaceBlockParam],
  );

  const clear = useCallback(() => {
    setActiveBlockIndex(null);
    replaceBlockParam(null);
  }, [replaceBlockParam]);

  const next = useCallback(() => {
    if (changedBlockIndices.length === 0) {
      return;
    }

    const currentPosition =
      safeActiveBlockIndex === null ? -1 : changedBlockIndices.indexOf(safeActiveBlockIndex);
    const nextPosition =
      currentPosition === -1
        ? 0
        : Math.min(currentPosition + 1, changedBlockIndices.length - 1);

    // Stop at the ends instead of wrapping so repeated keypresses do not
    // disorient a long-form reader by jumping from the end back to the start.
    goTo(changedBlockIndices[nextPosition]);
  }, [safeActiveBlockIndex, changedBlockIndices, goTo]);

  const previous = useCallback(() => {
    if (changedBlockIndices.length === 0) {
      return;
    }

    const currentPosition =
      safeActiveBlockIndex === null
        ? changedBlockIndices.length
        : changedBlockIndices.indexOf(safeActiveBlockIndex);
    const previousPosition =
      currentPosition === -1
        ? changedBlockIndices.length - 1
        : Math.max(currentPosition - 1, 0);

    goTo(changedBlockIndices[previousPosition]);
  }, [safeActiveBlockIndex, changedBlockIndices, goTo]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const initialBlock = parseBlockParam(
      new URLSearchParams(window.location.search).get("block"),
      comparisonSize,
    );

    if (initialBlock === null) {
      replaceBlockParam(null);
      return;
    }

    // Wait for the block to arrive rather than discarding the link. Stripping
    // ?block= here because the target sits in an unloaded window is how a
    // shared citation into a long manuscript silently becomes a link to the
    // top of the document.
    if (initialBlock >= blocks.length) {
      return;
    }

    if (!hasFocusedInitialBlock.current) {
      hasFocusedInitialBlock.current = true;
      focusBlock(initialBlock);
    }
  }, [blocks.length, comparisonSize, focusBlock, replaceBlockParam]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }

      if (isEditableTarget(event.target)) {
        return;
      }

      if (event.key === "j" || event.key === "n") {
        event.preventDefault();
        next();
        return;
      }

      if (event.key === "k" || event.key === "p") {
        event.preventDefault();
        previous();
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        clear();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clear, next, previous]);

  return {
    changedBlockIndices,
    activeBlockIndex: safeActiveBlockIndex,
    activeChangedPosition,
    totalChanges: changedBlockIndices.length,
    next,
    previous,
    goTo,
    clear,
  };
}
