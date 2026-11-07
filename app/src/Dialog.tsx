import { ReactNode, useRef } from "react";
import { useDialog } from "./barrierefrei";

/** Rahmen für einen Dialog: Fokus hinein, Tab bleibt drin, Escape schließt, danach Fokus zurück (siehe useDialog). */
export default function Dialog({
  label,
  onSchliessen,
  className,
  rolle = "dialog",
  children,
}: {
  label: string;
  onSchliessen?: () => void;
  className?: string;
  rolle?: "dialog" | "alertdialog";
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useDialog(ref, onSchliessen);
  return (
    <div ref={ref} className={className} role={rolle} aria-modal="true" aria-label={label} tabIndex={-1}>
      {children}
    </div>
  );
}
