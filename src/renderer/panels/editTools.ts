import { FEATURE_VIEWS } from '../features/registry';
import type { FeatureView } from '../features/types';
import type { ToolDefinition } from '../tools/framework/types';

/**
 * The tool that edits each feature type: the feature view names it, or else the
 * first tool that declares the type in `edits`.
 */
export function featureEditTools(
  views: Iterable<FeatureView> = FEATURE_VIEWS.values(),
  tools: readonly ToolDefinition[] = [],
): Map<string, string> {
  const result = new Map<string, string>();
  for (const tool of tools) {
    for (const type of tool.edits ?? []) if (!result.has(type)) result.set(type, tool.id);
  }
  for (const view of views) if (view.editTool) result.set(view.type, view.editTool);
  return result;
}
