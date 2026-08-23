# Website art review

The project website is reviewed against the visual direction in [`DESIGN.md`](../DESIGN.md). Screenshots are captured at desktop and mobile sizes, with the relay inspected both in motion and in its reduced-motion final state.

## Round 1

Overall direction: strong. The ledger-relay concept reads immediately, the cool-white/ink/cobalt palette is disciplined, and the asymmetric composition avoids a generic product-card layout.

Promoted refinements:

- **A1 — Reduced-motion control affordance:** the disabled “Flow shown” control looked too similar to an active replay button. Give the disabled state a quieter surface and default cursor so the static state is unambiguous.
- **A1 — Narrow-screen relay toolbar:** status copy and replay control shared one row at phone widths. Stack them to preserve reading order and avoid a cramped 320–390 px layout.
- **A1 — Strict-policy clipboard fallback:** the fallback used inline styles, which conflict with the site’s strict Content Security Policy. Move those declarations into the stylesheet.

No A0 issues were found. The motion uses only transform and opacity, and the mobile relay changes topology from horizontal to vertical rather than shrinking the desktop diagram.

## Round 2

The three promoted findings are resolved. Desktop and mobile compositions remain balanced, focus-visible styles are present, reduced motion presents a complete static diagram, and browser console/error checks are clean.

## Hero refinement

The desktop headline scale was reduced and the hero's top inset tightened so the thesis and ledger begin as one composition. The ledger explains append order on an 8-second loop with a settled pause and content-only fade before every reset. It returns to a complete static state while off-screen or the tab is hidden, restarts on re-entry, and stays permanently static for reduced-motion users.
