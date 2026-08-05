/**
 * A PDF with pages and no text layer, which is what a scan is.
 *
 * Built here rather than committed as a binary for the same reason the other
 * specs write their .md and .txt witnesses inline: a reviewer can see why this
 * file has no text without opening it in something. The absence is the whole
 * point of the fixture, and it is one line below — no /Contents on any page.
 *
 * Mirrors backend/tests/pdf_builder.py:build_scanned_pdf, which produces the
 * same shape for the parser's own tests.
 */
export function buildScannedPdf(pageCount = 2): Buffer {
  const objects: string[] = [];
  const add = (body: string) => {
    objects.push(body);
    return objects.length;
  };

  // The Pages object must name its kids and each kid its parent, so one id has
  // to be predicted. Pages is written after the pages themselves.
  const pagesId = pageCount + 1;
  const pageIds: number[] = [];
  for (let index = 0; index < pageCount; index += 1) {
    pageIds.push(
      add(
        `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 612 792] /Resources << >> >>`,
      ),
    );
  }

  const kids = pageIds.map((id) => `${id} 0 R`).join(" ");
  const actualPagesId = add(`<< /Type /Pages /Count ${pageIds.length} /Kids [${kids}] >>`);
  const catalogId = add(`<< /Type /Catalog /Pages ${actualPagesId} 0 R >>`);

  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, index) => {
    offsets.push(out.length);
    out += `${index + 1} 0 obj\n${body}\nendobj\n`;
  });

  const xrefOffset = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) {
    out += `${offset.toString().padStart(10, "0")} 00000 n \n`;
  }
  out += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\n`;
  out += `startxref\n${xrefOffset}\n%%EOF\n`;

  // latin1: every byte written above is ASCII, and the xref offsets counted
  // above are byte offsets. Encoding as UTF-8 would keep them correct only by
  // accident of that fact; latin1 makes the one-byte-per-character assumption
  // explicit rather than lucky.
  return Buffer.from(out, "latin1");
}
