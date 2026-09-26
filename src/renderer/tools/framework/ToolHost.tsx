import { useTools } from '../../state/toolStore';
import { toolById } from './registry';
import { closeTool } from './toolActions';

/** Renders the active panel tool; returns null when no panel tool is open. */
export function ToolHost() {
  const activeToolId = useTools((state) => state.activeToolId);
  const activation = useTools((state) => state.activation);
  const editTarget = useTools((state) => state.editTarget);
  const tool = activeToolId ? toolById(activeToolId) : undefined;
  if (!tool?.Panel) return null;
  const { Panel } = tool;
  return (
    <Panel
      key={`${tool.id}:${editTarget ?? ''}`}
      activation={activation}
      editTarget={editTarget}
      close={() => void closeTool({ force: true })}
    />
  );
}
