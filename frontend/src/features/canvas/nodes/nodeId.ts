let nodeSequence = 0;

export function createCanvasNodeId() {
  nodeSequence = (nodeSequence + 1) % Number.MAX_SAFE_INTEGER;
  const timestamp = Date.now().toString(36);
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `node-${timestamp}-${nodeSequence.toString(36)}-${randomPart}`;
}
