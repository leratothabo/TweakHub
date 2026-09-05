"use client";

import { PaymentMethod } from "@/lib/api";

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "card", label: "Card" },
  { value: "mtn_momo", label: "MTN MoMo" },
  { value: "airtel_money", label: "Airtel Money" },
  { value: "mpesa", label: "M-Pesa" },
  { value: "orange_money", label: "Orange Money" },
  { value: "wave", label: "Wave" },
  { value: "bank_transfer", label: "Bank Transfer" },
];

interface Props {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
}

/** Payment method picker for DPO Group's supported rails. */
export default function PaymentMethodSelector({ value, onChange }: Props) {
  return (
    <div style={styles.row}>
      {METHODS.map((m) => (
        <button
          key={m.value}
          onClick={() => onChange(m.value)}
          style={{
            ...styles.chip,
            borderColor: value === m.value ? "var(--accent-2)" : "var(--border)",
            color: value === m.value ? "var(--accent-2)" : "var(--text-muted)",
          }}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  row: { display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 },
  chip: {
    padding: "6px 12px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    fontSize: 13,
    fontWeight: 600,
  },
};
