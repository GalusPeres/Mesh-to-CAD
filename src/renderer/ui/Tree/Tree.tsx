import { ChevronDown, ChevronRight, type LucideIcon } from 'lucide-react';
import { type KeyboardEvent, type ReactNode, useState } from 'react';

import { classNames } from '../../lib/classNames';
import styles from './Tree.module.css';

export interface TreeNode {
  id: string;
  label: string;
  /** Muted text after the label (triangle count, file name). */
  secondary?: string;
  icon?: LucideIcon;
  /** Trailing status (warning or error icon). */
  status?: ReactNode;
  muted?: boolean;
  children?: TreeNode[];
  testId?: string;
}

export interface TreeProps {
  nodes: TreeNode[];
  label: string;
  selectedId?: string | null;
  defaultExpanded?: readonly string[];
  onSelect?: (id: string) => void;
  onActivate?: (id: string) => void;
  onHover?: (id: string | null) => void;
}

interface Row {
  node: TreeNode;
  depth: number;
  parentId: string | null;
}

function visibleRows(
  nodes: TreeNode[],
  expanded: Set<string>,
  depth = 0,
  parentId: string | null = null,
): Row[] {
  return nodes.flatMap((node) => [
    { node, depth, parentId },
    ...(node.children && expanded.has(node.id)
      ? visibleRows(node.children, expanded, depth + 1, node.id)
      : []),
  ]);
}

/** A `role="tree"` with arrow-key navigation; rows are 24 px, indent 16 px. */
export function Tree({
  nodes,
  label,
  selectedId,
  defaultExpanded = [],
  onSelect,
  onActivate,
  onHover,
}: TreeProps) {
  const [expanded, setExpanded] = useState(() => new Set(defaultExpanded));
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rows = visibleRows(nodes, expanded);

  const toggle = (id: string, open?: boolean) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (open ?? !next.has(id)) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = rows.findIndex((row) => row.node.id === (focusedId ?? selectedId));
    const row = rows[index];
    const move = (target: Row | undefined) => {
      if (!target) return;
      event.preventDefault();
      setFocusedId(target.node.id);
      onSelect?.(target.node.id);
    };
    switch (event.key) {
      case 'ArrowDown':
        move(rows[index + 1] ?? rows[0]);
        break;
      case 'ArrowUp':
        move(rows[Math.max(0, index - 1)]);
        break;
      case 'ArrowRight':
        if (row?.node.children?.length) toggle(row.node.id, true);
        break;
      case 'ArrowLeft':
        if (row && expanded.has(row.node.id)) toggle(row.node.id, false);
        else move(rows.find((candidate) => candidate.node.id === row?.parentId));
        break;
      case 'Enter':
        if (row) onActivate?.(row.node.id);
        break;
    }
  };

  return (
    <div role="tree" aria-label={label} tabIndex={0} className={styles.tree} onKeyDown={onKeyDown}>
      {rows.map(({ node, depth }) => {
        const hasChildren = !!node.children?.length;
        const isOpen = expanded.has(node.id);
        const Chevron = isOpen ? ChevronDown : ChevronRight;
        const Icon = node.icon;
        return (
          <div
            key={node.id}
            role="treeitem"
            aria-level={depth + 1}
            aria-selected={node.id === selectedId}
            aria-expanded={hasChildren ? isOpen : undefined}
            data-testid={node.testId}
            className={classNames(
              styles.row,
              node.id === selectedId && styles.selected,
              node.muted && styles.muted,
            )}
            style={{ paddingLeft: 4 + depth * 16 }}
            onClick={() => onSelect?.(node.id)}
            onDoubleClick={() => onActivate?.(node.id)}
            onMouseEnter={() => onHover?.(node.id)}
            onMouseLeave={() => onHover?.(null)}
          >
            <span
              className={styles.chevron}
              onClick={(event) => {
                event.stopPropagation();
                if (hasChildren) toggle(node.id);
              }}
            >
              {hasChildren && <Chevron size={16} aria-hidden />}
            </span>
            {Icon && <Icon className={styles.icon} size={16} aria-hidden />}
            <span
              className={styles.label}
              title={typeof node.label === 'string' ? node.label : undefined}
            >
              {node.label}
            </span>
            {node.secondary && (
              <span
                className={styles.secondary}
                title={typeof node.secondary === 'string' ? node.secondary : undefined}
              >
                {node.secondary}
              </span>
            )}
            {node.status}
          </div>
        );
      })}
    </div>
  );
}
