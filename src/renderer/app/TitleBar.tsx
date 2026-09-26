import { MenuBar } from './MenuBar';
import { StageTabs } from './StageTabs';
import styles from './TitleBar.module.css';

/** 32 px: app mark, menus, stage tabs; the rest drags the window. Caption buttons are native. */
export function TitleBar() {
  return (
    <header className={styles.bar}>
      <svg className={styles.mark} viewBox="0 0 16 16" aria-hidden>
        <path d="M2 12 8 2l6 10H2Z" />
        <path d="M5 12 8 7l3 5" />
      </svg>
      <MenuBar />
      <span className={styles.divider} />
      <StageTabs />
    </header>
  );
}
