import { CircleAlert, TriangleAlert } from 'lucide-react';

import { useMessages } from '../state/messageStore';
import type { StatusItem } from './status/types';
import styles from './StatusBar.module.css';

const modules = import.meta.glob<{ statusItem: StatusItem }>('../**/*.status.tsx', { eager: true });
const ITEMS = Object.values(modules)
  .map((module) => module.statusItem)
  .sort((a, b) => a.order - b.order);

/** Left: the current message. Right: status items in fixed order (selection, triangles, ...). */
export function StatusBar() {
  const message = useMessages((state) => state.current);
  const Icon =
    message?.severity === 'error'
      ? CircleAlert
      : message?.severity === 'warning'
        ? TriangleAlert
        : null;
  return (
    <footer className={styles.bar}>
      <div className={styles.message} role="status" aria-live="polite" data-testid="status-message">
        {Icon && <Icon size={16} className={styles[message?.severity ?? 'info']} aria-hidden />}
        {message?.text}
      </div>
      {ITEMS.map(({ Component }, index) => (
        <div key={index} className={styles.item}>
          <Component />
        </div>
      ))}
    </footer>
  );
}
