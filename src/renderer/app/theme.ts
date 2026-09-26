import type { ThemeSetting } from '@shared/settings';

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)');

export function resolveTheme(setting: ThemeSetting): 'dark' | 'light' {
  if (setting === 'system') return darkQuery().matches ? 'dark' : 'light';
  return setting;
}

/** Apply the theme to the document and the native title-bar buttons. */
export function applyTheme(setting: ThemeSetting): void {
  const theme = resolveTheme(setting);
  document.documentElement.dataset.theme = theme;
  const style = getComputedStyle(document.documentElement);
  const color = style.getPropertyValue('--bg-app').trim().toUpperCase();
  const symbolColor = style.getPropertyValue('--text').trim().toUpperCase();
  if (color && symbolColor) window.m2c.window.setTitleBarColors({ color, symbolColor });
}

/** Follow Windows' light/dark setting while the theme is "System". */
export function watchSystemTheme(current: () => ThemeSetting): () => void {
  const query = darkQuery();
  const onChange = () => {
    if (current() === 'system') applyTheme('system');
  };
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}
