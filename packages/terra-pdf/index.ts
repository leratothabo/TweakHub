/**
 * Still genuinely useful, unlike its avx-client/convert-agent siblings:
 * TerraPDF itself was never confirmed as a real project (see
 * docs/engines.md), but this file's job — building the JSON payload
 * apps/web posts as the `file` field for invoice_generator — matches
 * exactly what apps/api/services/engines/pdf_generate.py's real reportlab
 * -based handler expects. That engine recomputes the total from
 * lineItems itself rather than trusting this one, so a mismatch here is
 * just a display issue, not a pricing bug.
 */
export interface InvoiceTemplateData {
  invoiceNumber: string;
  issueDate: string;
  dueDate: string;
  lineItems: { description: string; quantity: number; unitPrice: number }[];
  currency: "USD" | "ZAR" | "KES";
}

export function buildInvoicePayload(data: InvoiceTemplateData) {
  const total = data.lineItems.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
  return { ...data, total };
}
