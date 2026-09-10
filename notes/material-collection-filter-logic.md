# Material filter ↔ collection lock logic (mobile-v36.html)

Canonical write-up of how the material-type row (Neted / Texturat / Catifea / Efect catifea)
interacts with collection locking and multi-zone coloring, and why it's built the way it is.
Written after a session of live-testing surfaced three real bugs in this interaction, fixed in
sequence (commits `08bdb9f` → `7895cad` → `7a93857` → `0d27241` on `main`). Come back here before
touching any of this again — the history matters, the earlier "fixes" were each wrong in a
specific, instructive way.

## The state involved

```js
var sel = {
  collectionSlug: null,     // which collection the grid currently reads as "the" fabric
  collectionLocked: false,  // true only if the shopper EXPLICITLY picked a collection card
  zoneMode: false,          // "Canapea în culori diferite" toggle
  zones: {},                // per-zone colour when zoneMode is on
  ...
};
var activeFabricPills = []; // keys from FABRIC_PILLS the material-type row has checked
var MATERIAL_AVAILABLE;     // {key: bool} -- recomputed by applyFabricFilters()
```

- `FABRIC_PILLS` (~line 1590) is the material-type catalog: `neted`, `texturat`, `catifea`,
  `efect-catifea`, each with `stems` used to match against a collection's `materialTypes`.
- Every `COLLECTIONS[slug]` has a `materialTypes` array (e.g. `piano.materialTypes = ['Catifea']`,
  `manila.materialTypes = ['Efect catifea']`) — this is the ground truth for "what is this
  collection, materially".

## `collectionNarrowed()` (line 2020)

```js
function collectionNarrowed(){
  return !SUSPEND_COLLECTION_NARROW && !!sel.collectionSlug && (sel.collectionLocked || sel.zoneMode);
}
```

True when the color grid is pinned to exactly one collection — because the shopper explicitly
locked one (`collectionLocked`), or because zone-coloring is on and every zone has to come from
the same fabric. **While this is true, the material-type row does nothing** — the grid ignores it
regardless of what's checked. This was always the design; the bugs were all about the row failing
to *look* like it does nothing.

## Two ways `collectionSlug` gets set — only one of them is a real decision

- `pickCollection(slug)` (line 3006) — tapping a collection card. Sets `collectionLocked = true`.
  This is an explicit choice.
- `pickFabricSwatch(el, slug)` (line 3076) — tapping an individual swatch tile while browsing
  broadly (zoneMode off). Sets `sel.collectionSlug = slug` **without** locking it. The shopper is
  still browsing the whole catalogue; the collection is just "whatever fabric that swatch happens
  to belong to", not a commitment.

That second path is the one that caused the deepest bug (see Bug 3 below): `collectionNarrowed()`
used to treat both cases identically once `zoneMode` was on, even though only the first one is
actually a decision.

## The three bugs, in the order they were found

### Bug 1 — checked + disabled contradiction
Original behavior: when a collection got locked while a material pill was active, the pill stayed
checked (`.on`) but also got greyed via `.is-unavailable` if `MATERIAL_AVAILABLE` disagreed. Visibly
contradictory — a tile reading "this is your choice" and "this is unavailable" at once.

### Fix attempt 1 — blanket clear (commit `7895cad`) — **overcorrected**
First fix: whenever `collectionNarrowed()` becomes true, wipe `activeFabricPills` to `[]`. This
killed the contradiction, but also threw away *correct* information: locking **Piano** (which
really is `Catifea`) while **Catifea** was checked would clear it anyway — even though keeping it
checked would've been simply true. Caught via live user testing, not review.

### Fix 2 — sync to truth, not clear (commit `7a93857`) — **correct**
`clearMaterialFilterIfNarrowed()` (line 2993) now does this instead of clearing:

```js
function clearMaterialFilterIfNarrowed(){
  if (!collectionNarrowed()) return;
  var c = COLLECTIONS[sel.collectionSlug];
  var truth = FABRIC_PILLS.filter(function(p){
    return p.stems.some(function(stem){ return c.materialTypes.some(function(t){ return t.indexOf(stem) > -1; }); });
  }).map(function(p){ return p.key; });
  var changed = truth.length !== activeFabricPills.length || truth.some(function(k){ return activeFabricPills.indexOf(k) === -1; });
  if (changed){
    activeFabricPills = truth;
    renderFabricPillRow();
    renderFsheetMaterialPill();
  }
}
```

Called from both `pickCollection()` and `toggleZoneMode()`. The row is resynced to what the locked
collection *actually is*, not blanked. A true match (Manila → Efect catifea) stays checked and,
via the existing `applyFabricFilters()` call right after, correctly shows as available (not
greyed) since `availableMaterials()` agrees. A real mismatch (Piano locked while Neted was checked)
swaps to the true one (Catifea) instead of lingering on the wrong, now-inert pill.

Also added in this pass: `buildFabricSeg`'s `onclick` (line ~1970) now re-checks
`collectionNarrowed()` live before toggling anything, instead of trusting only the rendered
`.is-unavailable` class — closes a race where a pill could still be clicked into a selected state
one render behind an availability change.

### Fix 3 — root cause: don't narrow on a merely-inferred collection (commit `0d27241`)
Even with Fix 2 being logically correct, testing surfaced the real problem one layer down:
`toggleZoneMode()` (line 2886) narrowed against **any** leftover `sel.collectionSlug`, locked or
not. So browsing a Piano swatch (inferred only, `collectionLocked` still `false`), then checking
a material filter, then flipping "Canapea în culori diferite" on would silently pin the whole
zone-flow to Piano and swap the material filter to match it — **two decisions the shopper never
made**, sprung on them by a toggle that has nothing to do with collections on its face.

Fix, inside `toggleZoneMode()`:

```js
if (sel.zoneMode){
  ZONES.forEach(function(z){ sel.zones[z.key] = sel.colorName; });
  sel.zone = 'sezut';
  // Reset an inferred-but-never-locked collection -- it was never a real choice.
  if (!sel.collectionLocked) sel.collectionSlug = null;
} else {
  ...
}
```

Entering zone mode now only stays narrowed to a collection if it was **explicitly locked**
beforehand. Otherwise `collectionSlug` resets to `null`, so "Alege colecția pentru toate zonele"
is a genuine prompt — same as a first-time visit — instead of a formality over a choice already
made behind the shopper's back.

## Invariants now guaranteed (verified live, not just read)

1. A material pill can never be `.on` **and** `.is-unavailable` at the same time.
2. Locking a collection that matches an active filter (Manila↔Efect catifea, Piano↔Catifea) keeps
   that filter checked and enabled — no false negative.
3. Locking a collection that contradicts the active filter swaps the display to the true material
   type instead of leaving the wrong one checked.
4. Clicking a material pill while `collectionNarrowed()` is true is a no-op, checked live at click
   time (not from a stale render).
5. Turning zone-coloring on never silently locks a collection the shopper only browsed past —
   only an explicit collection-card tap (`pickCollection`) can set `collectionLocked = true`.

## How to re-verify by hand

In the browser console on `mobile-v36.html`, in the Culoare section:

```js
// Bug-3 repro (should now be a no-op / clean reset):
sel.collectionSlug = 'piano'; sel.collectionLocked = false; // simulate "merely browsed"
document.querySelector('#cfg-fabric-pillrow .cfg-seg[data-key="texturat"]').click();
toggleZoneMode();
// expect: sel.collectionSlug === null, activeFabricPills === ['texturat'] still on
```

```js
// Truthful-match repro:
var manila = Object.keys(COLLECTIONS).filter(s => COLLECTIONS[s].name === 'Manila')[0];
document.querySelector('#cfg-fabric-pillrow .cfg-seg[data-key="efect-catifea"]').click();
pickCollection(manila);
// expect: efect-catifea pill class is "cfg-seg vert on" -- NOT is-unavailable
```

## Files touched

- `mobile-v36.html` only. `mobile-v35.html` was deliberately left with the original (pre-vertical-
  card) material row and title styling — see the v35/v36 split earlier in this session.
