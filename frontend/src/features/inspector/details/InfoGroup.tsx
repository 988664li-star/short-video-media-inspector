import type { ReactNode } from "react";

import { displayValue, hasValue } from "../../../lib/formatters";


export type InfoRow = readonly [label: string, value: unknown];

interface InfoGroupProps {
  title: string;
  rows: InfoRow[];
  children?: ReactNode;
  className?: string;
}

export function InfoGroup({ title, rows, children, className = "" }: InfoGroupProps) {
  const availableRows = rows.filter(([, value]) => hasValue(value));
  if (!availableRows.length && !children) return null;
  return (
    <section className={`info-group ${className}`.trim()}>
      <h3>{title}</h3>
      {availableRows.length ? (
        <dl className="info-list">
          {availableRows.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd>{displayValue(value)}</dd></div>
          ))}
        </dl>
      ) : null}
      {children}
    </section>
  );
}
