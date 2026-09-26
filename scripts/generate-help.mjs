// Generates the offline help pages in resources/help/<language>/ (docs/DESIGN.md 5.10).
//
// Every tool gets a page from its own strings (tools/<id>/locales: label, tooltip and
// the "So geht's" text), the index lists the tools by stage, getting-started is
// rendered from docs/user, and licenses from THIRD_PARTY_NOTICES.md. The pages are
// plain HTML with the application's colours and no external resources.
//
//   node scripts/generate-help.mjs          write the pages
//   node scripts/generate-help.mjs --check  fail if the pages are out of date

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import * as prettier from 'prettier';

import { root } from './paths.mjs';

const LANGUAGES = ['de', 'en'];
const OUTPUT = path.join(root, 'resources', 'help');
const RENDERER = path.join(root, 'src', 'renderer');
const STAGES = ['prepare', 'align', 'model', 'inspect'];
const GROUP_ORDER = [
  'selection',
  'mesh',
  'analysis',
  'regions',
  'align',
  'fit',
  'reference',
  'sketch',
  'solid',
  'freeform',
  'inspect',
  'export',
];

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));

const escapeHtml = (text) =>
  String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');

/** Colour tokens of both themes, read from the application's tokens.css. */
function themeColours() {
  const css = readFileSync(path.join(RENDERER, 'styles', 'tokens.css'), 'utf8');
  const block = (theme) => {
    const start = css.indexOf(`[data-theme='${theme}']`);
    const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start));
    return Object.fromEntries(
      [...body.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)].map((match) => [match[1], match[2]]),
    );
  };
  return { light: block('light'), dark: block('dark') };
}

function styleSheet({ light, dark }) {
  const variables = (colours) =>
    ['bg-panel', 'bg-raised', 'text', 'text-secondary', 'accent-text', 'border', 'border-subtle']
      .map((name) => `--${name}: ${colours[name]};`)
      .join(' ');
  return `
    :root { ${variables(light)} }
    @media (prefers-color-scheme: dark) { :root { ${variables(dark)} } }
    body { margin: 0; background: var(--bg-panel); color: var(--text);
      font: 14px/1.5 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; }
    main { max-width: 760px; margin: 0 auto; padding: 24px 32px 48px; }
    h1 { font-size: 20px; font-weight: 600; margin: 0 0 16px; }
    h2 { font-size: 16px; font-weight: 600; margin: 32px 0 8px; }
    h3 { font-size: 14px; font-weight: 600; margin: 24px 0 8px; }
    a { color: var(--accent-text); }
    nav { font-size: 13px; margin-bottom: 16px; }
    code, kbd { font-family: "Cascadia Mono", Consolas, monospace; font-size: 13px; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { text-align: left; padding: 4px 12px 4px 0; border-bottom: 1px solid var(--border-subtle);
      vertical-align: top; }
    th { font-weight: 600; }
    .secondary { color: var(--text-secondary); }
    ul.tools { list-style: none; padding: 0; }
    ul.tools li { padding: 4px 0; border-bottom: 1px solid var(--border-subtle); }
  `;
}

/** Inline Markdown: code, bold, italic and links. The text is escaped first. */
function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])_([^_]+)_/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label, href) => {
      const target = href.replace(/^getting-started(\.de)?\.md$/, 'getting-started.html');
      return `<a href="${target}">${label}</a>`;
    });
}

/**
 * The Markdown the user guides and THIRD_PARTY_NOTICES.md use: headings, paragraphs,
 * ordered and unordered lists (with continuation lines) and tables.
 */
function markdownToHtml(markdown) {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let index = 0;
  const cells = (line) =>
    line
      .trim()
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((cell) => cell.trim());
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
    } else if (/^#{1,3} /.test(line)) {
      const level = line.indexOf(' ');
      out.push(`<h${level}>${inline(line.slice(level + 1))}</h${level}>`);
      index += 1;
    } else if (line.startsWith('|')) {
      const header = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].startsWith('|')) rows.push(cells(lines[index++]));
      out.push(
        `<table><thead><tr>${header.map((cell) => `<th>${inline(cell)}</th>`).join('')}</tr></thead>`,
        `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table>`,
      );
    } else if (/^(\d+\.|-) /.test(line)) {
      const ordered = /^\d+\./.test(line);
      const items = [];
      while (index < lines.length && /^(\d+\.|-) /.test(lines[index])) {
        let item = lines[index].replace(/^(\d+\.|-) /, '');
        index += 1;
        while (index < lines.length && /^ {2,}\S/.test(lines[index])) {
          item += ` ${lines[index].trim()}`;
          index += 1;
        }
        items.push(`<li>${inline(item)}</li>`);
      }
      out.push(ordered ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`);
    } else {
      const paragraph = [];
      while (
        index < lines.length &&
        lines[index].trim() &&
        !/^(#|\||\d+\. |- )/.test(lines[index])
      ) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      out.push(`<p>${inline(paragraph.join(' '))}</p>`);
    }
  }
  return out.join('\n');
}

/** Stage, group, shortcut and status of each tool, read from its definition. */
function toolDefinitions() {
  const folder = path.join(RENDERER, 'tools');
  return readdirSync(folder, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'framework')
    .flatMap((entry) => {
      const file = ['index.ts', 'index.tsx']
        .map((name) => path.join(folder, entry.name, name))
        .find(existsSync);
      if (!file) return [];
      const source = readFileSync(file, 'utf8');
      const stages = /stages:\s*\[([^\]]*)\]/.exec(source)?.[1] ?? '';
      const shortcut = /shortcut:\s*\{([^}]*)\}/.exec(source)?.[1] ?? null;
      return [
        {
          id: entry.name,
          stages: [...stages.matchAll(/'([a-z]+)'/g)].map((match) => match[1]),
          group: /group:\s*'([a-z]+)'/.exec(source)?.[1] ?? 'mesh',
          ready: /status:\s*'ready'/.test(source),
          shortcut: shortcut && {
            key: /key:\s*'([^']+)'/.exec(shortcut)?.[1],
            ctrl: /ctrl:\s*true/.test(shortcut),
            shift: /shift:\s*true/.test(shortcut),
          },
          strings: Object.fromEntries(
            LANGUAGES.map((language) => {
              const locale = path.join(folder, entry.name, 'locales', `${language}.json`);
              return [language, existsSync(locale) ? readJson(locale) : {}];
            }),
          ),
        },
      ];
    })
    .sort(
      (a, b) =>
        GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group) || a.id.localeCompare(b.id),
    );
}

function shortcutText(shortcut, language) {
  if (!shortcut?.key) return null;
  const parts = [];
  if (shortcut.ctrl) parts.push(language === 'de' ? 'Strg' : 'Ctrl');
  if (shortcut.shift) parts.push(language === 'de' ? 'Umschalt' : 'Shift');
  parts.push(shortcut.key.length === 1 ? shortcut.key.toUpperCase() : shortcut.key);
  return parts.join('+');
}

function page({ language, title, body, css, pages, backLink = true }) {
  return `<!doctype html>
<html lang="${language}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)} – ${escapeHtml(pages.title)}</title><style>${css}</style></head>
<body><main>
${backLink ? `<nav><a href="index.html">${escapeHtml(pages.back)}</a></nav>` : ''}
${body}
</main></body></html>`;
}

function buildPages(language, tools, css) {
  const common = readJson(path.join(RENDERER, 'i18n', 'locales', language, 'common.json'));
  const pages = readJson(path.join(RENDERER, 'help', 'locales', `${language}.json`)).pages;
  const label = (tool) => tool.strings[language].label ?? tool.id;
  const stageNames = (tool) =>
    tool.stages.length ? tool.stages.map((stage) => common.stages[stage]).join(', ') : pages.file;
  const files = new Map();

  for (const tool of tools) {
    const strings = tool.strings[language];
    const howTo = strings.howTo ?? strings.help;
    const shortcut = shortcutText(tool.shortcut, language);
    const rows = [
      [pages.stage, stageNames(tool)],
      ...(shortcut ? [[pages.shortcut, `<kbd>${escapeHtml(shortcut)}</kbd>`]] : []),
    ];
    const body = [
      `<h1>${escapeHtml(label(tool))}</h1>`,
      strings.tooltip ? `<p class="secondary">${escapeHtml(strings.tooltip)}</p>` : '',
      tool.ready ? '' : `<p class="secondary">${escapeHtml(pages.notAvailable)}</p>`,
      `<table><tbody>${rows.map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${key === pages.shortcut ? value : escapeHtml(value)}</td></tr>`).join('')}</tbody></table>`,
      `<h2>${escapeHtml(pages.howTo)}</h2>`,
      `<p>${escapeHtml(howTo ?? pages.noDescription)}</p>`,
    ].join('\n');
    files.set(`${tool.id}.html`, page({ language, title: label(tool), body, css, pages }));
  }

  const toolList = (list) =>
    `<ul class="tools">${list
      .map(
        (tool) =>
          `<li><a href="${tool.id}.html">${escapeHtml(label(tool))}</a>` +
          (tool.strings[language].tooltip
            ? ` <span class="secondary">${escapeHtml(tool.strings[language].tooltip)}</span>`
            : '') +
          '</li>',
      )
      .join('')}</ul>`;
  const byStage = STAGES.map((stage) => {
    const list = tools.filter((tool) => tool.stages[0] === stage);
    return list.length ? `<h3>${escapeHtml(common.stages[stage])}</h3>${toolList(list)}` : '';
  });
  const fileTools = tools.filter((tool) => tool.stages.length === 0);
  const index = [
    `<h1>${escapeHtml(pages.title)}</h1>`,
    `<p>${escapeHtml(pages.intro)}</p>`,
    `<p><a href="getting-started.html">${escapeHtml(pages.gettingStarted)}</a> <span class="secondary">${escapeHtml(pages.gettingStartedText)}</span></p>`,
    `<h2>${escapeHtml(pages.tools)}</h2>`,
    fileTools.length ? `<h3>${escapeHtml(pages.file)}</h3>${toolList(fileTools)}` : '',
    ...byStage,
    `<h2>${escapeHtml(pages.mouse)}</h2>`,
    `<table><tbody>${pages.mouseRows.map(([action, input]) => `<tr><th>${escapeHtml(action)}</th><td>${escapeHtml(input)}</td></tr>`).join('')}</tbody></table>`,
    `<p><a href="licenses.html">${escapeHtml(pages.licenses)}</a></p>`,
  ].join('\n');
  files.set(
    'index.html',
    page({ language, title: pages.overview, body: index, css, pages, backLink: false }),
  );

  const guide = language === 'de' ? 'getting-started.de.md' : 'getting-started.md';
  const guideMarkdown = readFileSync(path.join(root, 'docs', 'user', guide), 'utf8');
  files.set(
    'getting-started.html',
    page({
      language,
      title: pages.gettingStarted,
      body: markdownToHtml(guideMarkdown),
      css,
      pages,
    }),
  );

  const notices = readFileSync(path.join(root, 'THIRD_PARTY_NOTICES.md'), 'utf8');
  files.set(
    'licenses.html',
    page({
      language,
      title: pages.licenses,
      body: `${markdownToHtml(notices)}\n<p>${escapeHtml(pages.licensesText)}</p>`,
      css,
      pages,
    }),
  );
  return files;
}

async function main() {
  const check = process.argv.includes('--check');
  const css = styleSheet(themeColours());
  const tools = toolDefinitions();
  const options = {
    ...(await prettier.resolveConfig(path.join(OUTPUT, 'index.html'))),
    parser: 'html',
  };
  const stale = [];
  for (const language of LANGUAGES) {
    const folder = path.join(OUTPUT, language);
    const files = buildPages(language, tools, css);
    if (!check) {
      rmSync(folder, { recursive: true, force: true });
      mkdirSync(folder, { recursive: true });
    }
    for (const [name, html] of files) {
      const formatted = await prettier.format(html, options);
      const file = path.join(folder, name);
      if (check) {
        if (!existsSync(file) || readFileSync(file, 'utf8') !== formatted) stale.push(file);
      } else {
        writeFileSync(file, formatted);
      }
    }
    const missing = tools.filter(
      (tool) => !(tool.strings[language].howTo ?? tool.strings[language].help),
    );
    if (missing.length) {
      console.warn(
        `${language}: no "So geht's" text for ${missing.map((tool) => tool.id).join(', ')}`,
      );
    }
  }
  if (check && stale.length) {
    console.error(
      `Help pages are out of date; run node scripts/generate-help.mjs:\n${stale.join('\n')}`,
    );
    process.exit(1);
  }
  console.log(check ? 'Help pages are up to date.' : `Wrote help pages for ${tools.length} tools.`);
}

await main();
