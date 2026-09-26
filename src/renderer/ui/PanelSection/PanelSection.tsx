import { ChevronDown, ChevronRight } from 'lucide-react';
import { type ReactNode, useId, useState } from 'react';

import styles from './PanelSection.module.css';

export interface PanelSectionProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  /** Controlled state, e.g. remembered per tool in the settings. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function PanelSection({
  title,
  children,
  defaultOpen = true,
  open,
  onOpenChange,
}: PanelSectionProps) {
  const [localOpen, setLocalOpen] = useState(defaultOpen);
  const isOpen = open ?? localOpen;
  const contentId = useId();
  const toggle = () => {
    setLocalOpen(!isOpen);
    onOpenChange?.(!isOpen);
  };
  const Chevron = isOpen ? ChevronDown : ChevronRight;
  return (
    <section className={styles.section}>
      <button
        type="button"
        className={styles.header}
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={toggle}
      >
        <Chevron size={16} aria-hidden />
        <span>{title}</span>
      </button>
      {isOpen && (
        <div id={contentId} className={styles.content}>
          {children}
        </div>
      )}
    </section>
  );
}
