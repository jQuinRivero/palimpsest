import { expect, type APIRequestContext } from "@playwright/test";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const alteredA =
  "It was the best of times, it was the worst of times.\n\n" +
  "It was the age of wisdom, it was the age of foolishness.\n\n" +
  "We had everything before us, we had nothing before us.";

export const alteredB =
  "It was the best of times, it was the strangest of times.\n\n" +
  "It was the age of wisdom, it was the bright age of foolishness.\n\n" +
  "We had everything before us, we had little before us.";

export const identicalWitness =
  "It was the best of times, it was the worst of times.\n\n" +
  "It was the age of wisdom, it was the age of foolishness.";

type DocumentSummary = {
  id: string;
};

type ComparisonResult = {
  comparison_id: string;
};

export async function uploadText(
  request: APIRequestContext,
  title: string,
  text: string,
): Promise<DocumentSummary> {
  const response = await request.post(`${API_BASE}/api/v1/documents`, {
    multipart: {
      title,
      file: {
        name: `${title}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from(text, "utf-8"),
      },
    },
  });

  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as DocumentSummary;
}

export async function createComparison(
  request: APIRequestContext,
  aText = alteredA,
  bText = alteredB,
): Promise<string> {
  const a = await uploadText(request, "Manuscript A", aText);
  const b = await uploadText(request, "Manuscript B", bText);

  const response = await request.post(`${API_BASE}/api/v1/comparisons`, {
    data: {
      a_document_id: a.id,
      b_document_id: b.id,
    },
  });

  expect(response.ok(), await response.text()).toBeTruthy();
  const comparison = (await response.json()) as ComparisonResult;
  return comparison.comparison_id;
}
