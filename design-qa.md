# Canvas node interaction design QA

- Source visual truth: conversation attachment showing Xiaoyunque node + attached prompt composer (1872 × 954 px; no filesystem path exposed by the chat renderer).
- Implementation screenshot: `/tmp/f2-canvas-node-follow-polished.png` (1280 × 720 px, device scale factor 1).
- Route: `/replication/canvas`.
- State: text node selected; contextual AI composer visible and attached to the selected node.
- Density normalization: component-level comparison; source and implementation use different full-page viewports, so the node/composer relationship was compared rather than raw page coordinates.

## Full-view comparison

The selected node is now the visual anchor. Its AI composer is rendered by React Flow's node toolbar layer rather than fixed to the browser viewport. The implementation preserves the application's dark design system while matching the source interaction hierarchy: compact result card, contextual composer, prompt, references, model, and primary generate action.

## Focused region comparison

- Node card: compact header, clear media/document body, restrained border and selected state.
- Composer: visually separate but spatially attached to the selected node.
- Boundary behavior: composer chooses above or below based on available canvas space, changes horizontal alignment near edges, and becomes internally scrollable when neither side can fit completely.
- Drag behavior: browser measurement confirmed the node and composer moved by the same screen delta and returned together when restored.

## Comparison history

1. P1: composer was fixed to the viewport and did not follow its node.
   - Fix: moved composer into a reusable `NodeToolbar`-backed component owned by each text/image node.
2. P1: composer could be clipped when a node was near a canvas edge.
   - Fix: added adaptive top/bottom placement, start/center/end alignment, and available-height scrolling.
3. P2: node and composer were visually oversized and form-heavy.
   - Fix: removed redundant result headings, tightened the card body, reduced composer density, and strengthened hierarchy.

## Required fidelity surfaces

- Typography: clear 700/650 hierarchy; compact helper text; no unwanted wrapping in the primary controls.
- Spacing/layout: node and composer remain separate, with a consistent 16 px contextual offset.
- Colors/tokens: dark canvas palette intentionally retained; coral is reserved for selection and primary action.
- Image quality: existing source images retain contain scaling and explicit full-size preview.
- Copy/content: labels describe node-local behavior and upstream references accurately.

## Remaining P3 polish

- A future iteration can add a compact collapse control to very tall image composers.

## Verification

- Primary interaction: select text/image node → local composer appears → drag node → composer follows with identical delta.
- Browser console: 0 errors, 0 warnings.
- Framework overlay: none.

final result: passed
