# Saved pagination, stamp settings and final publication seal

`publication_finalization.finalization_order` builds an explicit ordered offline
plan. `assess_finalized_publication` checks supplied saved evidence against it.
Neither function opens CAD, writes files, installs an SDK, retries a save, or
certifies the current product job. Product success must be read from that job's
actual final receipt; an intermediate findings note is not such a receipt.

## Finalization order

1. Finish COMMON specification formatting and Save while linked owned CDWs may
   still be rewritten. Complete specification row/header/formatting saves.
2. Read each **saved/reopened** SPW, verify API5 page count, physical page numbers,
   header count, native page styles, actual library identity and preserved rows.
   If the saved page count/header differ, stop and reconcile SPW finalization at
   this stage. Do not patch Text8 after sealing CDWs.
3. Serialize every owned one-file-per-logical-sheet CDW with explicit document
   numbering settings and mapped stamp fields, Stamp.Update and Save.
4. Seal the complete owned SPW+CDW byte set only after all writeback has finished.
5. Run one full saved-RO gate containing two distinct RO cycles. Compare the final
   hashes, originals, saved pagination/settings/stamps/libraries and strict
   preserved semantic fingerprints. Read hashes again at completion. No writes
   or automatic reseals are permitted between seal and completion.

SPW saves can rewrite attached CDW bytes even when only a header changed, no row
setter ran, and no explicit Rebuild was requested. Unchanged drawing semantics
or Changed=False does not establish unchanged bytes. The synthetic specification
save propagates byte changes into its attached drawing objects independently of
their properties, and a late save fails final hash validation.

## Explicit logical CDW numbering

Fresh CDW seeds can retain SheetAutoNumber=True. Assigning Stamp.Text(7) alone
can pass live readback but reset to the physical document page on saved reopen.
For the bounded one-file-per-logical-sheet strategy, the plan requires:

```text
IDrawingDocument.DocumentSettings -> typed IDrawingDocumentSettings
SheetAutoNumber = False
SheetFirstNumber = logical sheet number
SheetAutoCount = False
SheetsCount = logical family total
mapped Stamp fields, including Text7 = logical and Text8 = family total
Stamp.Update -> Save -> saved RO verification
```

The family plan must contain exactly one distinct CDW for each logical number
1..total. Saved settings, mapped stamp values and the CDW's single physical sheet
are all checked. A correct live Text7 is insufficient; implicit seed defaults or
boolean/numeric coercion in the declared operations are not accepted.

## Saved SPW pagination and page identity

Pre-Save LayoutSheets.Count or unsaved API5 pagination caches are not release
gates. WordWrap can change pagination during Save/reopen. The oracle uses the
saved API5 count, requires saved LayoutSheets.Count agreement and Text8 equal to
that count, then requires the same saved result through the final RO gate.

Physical SPW page identity comes from API5 `GetStampEx(i+1).SheetNumb`; the expected
sequence is 1..saved_count. Raw shared Stamp.Text7 is diagnostic, not a per-page
number oracle. Descriptor style and per-page styles are separate planned fields:
the first/continuation style sequence is checked without assuming that descriptor
StyleID must equal a physical page's style ID. These are caller-pinned style IDs,
not hardcoded product parameters.

## Actual style library identity

A same-GUID private clone can canonicalize to an installed library even when
content hashes match. SPW evidence must contain the **actual path and SHA**, and
its configured library path must agree with the verified actual installed path.
A matching SHA alone does not excuse a wrong path. The CDW library policy is
independent and can remain the verified private clone. No style library is
copied into this public SDK or changed by these functions.

## Strict scope and evidence limits

The plan pins disjoint originals and explicit unique owned files. Every saved
cycle must cover exactly the planned SPWs and CDWs. SPW row payload fingerprints
and CDW preserved semantic fingerprints remain pinned; re-pagination or new stamp
settings do not waive existing geometry/pose/UUID/constraint/row oracles. Native
collectors must compute these fingerprints from the unchanged strict semantic
checks and retain their full evidence. Opaque digests alone do not prove native
correctness; this module only checks their consistency and ordering claims.

No native executor is wired to the planner. Its operation records are an explicit
adapter contract, not proof of chronology. A successful result is
`consistent_offline_evidence`, with `native_acceptance='pending'` and no mutation
performed. Dynamic renumbering and full CAD-package portability remain unproved.
No product model, engineering value, private receipt or current product outcome
is incorporated into the synthetic fixtures.

The synthetic integration model covers fresh auto-number reset, saved WordWrap
repagination, a shared Text7 with distinct API5 physical page numbers, header-only
SPW save propagation, late writes after seal, actual-library path versus same SHA,
complete logical families and unchanged full-RO semantic fingerprints. Native
validation requires fresh discovery and explicit exclusive CAD handover.
