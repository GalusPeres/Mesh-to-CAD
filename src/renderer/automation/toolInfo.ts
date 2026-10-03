// What the open tool offers to automation clients beyond its panel: the things in
// the 3D view it lets the user grab (border edges of a net, points, handles), with
// their screen positions, so an assistant can drag them like the user would.

type ToolInfoProvider = () => unknown;

let provider: ToolInfoProvider | null = null;

/** Called by an open tool; the returned function removes the provider again. */
export function setToolInfoProvider(next: ToolInfoProvider): () => void {
  provider = next;
  return () => {
    if (provider === next) provider = null;
  };
}

/** The open tool's information, or null when it publishes none. */
export function toolInfo(): unknown {
  return provider ? provider() : null;
}
