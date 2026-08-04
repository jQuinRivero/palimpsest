/**
 * Shared contract for the virtualized reading surfaces.
 *
 * Synoptic and unified are two renderings of the same list of `DiffBlock`s,
 * so they answer to the same handle: navigation asks for a block index and
 * does not need to know which view is mounted.
 */
export interface BlockListHandle {
  /**
   * Bring a block into view.
   *
   * Navigation must call this rather than querying the DOM. A row outside the
   * rendered window has no element to scroll to, so a DOM-based jump fails
   * silently on exactly the long manuscripts virtualization exists for.
   */
  scrollToBlock: (index: number) => void;
}

/**
 * Overscan, in pixels, because that is the unit `react-virtuoso` takes.
 * Roughly a viewport of prose above and below the visible range.
 */
export const OVERSCAN_PX = 1200;
