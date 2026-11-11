# Object-local property commit contract

`object_commit.assess_object_commits` extends the offline regression model with
an explicit **setter -> changed object's own Update -> Save -> two saved RO**
sequence. It neither executes CAD nor changes installed clients/native helpers.
A successful result remains `consistent_offline_evidence`, with native acceptance
pending and no mutation performed by the oracle.

The bounded layer case is important: an immediate `ILayer.Printable=False` getter
can report False while the saved file still retains the old True value when the
changed layer was not updated. Updating its parent view does not substitute for
that missing layer Update. A view's Visible=False can persist independently while
the child's Printable reverts. The stateful synthetic backend has separate live
and committed buffers for both objects and reproduces that distinction.

The receipt requires:

- fully scoped unique changed-object keys and exact intended property values;
- an explicitly committed expected editing context before any setters;
- immediate getters matching the final setter values, with boolean False distinct
  from numeric zero;
- an Update event targeting **each changed object**, after its last setter and
  before Save; an ancestor's event does not count, and a later setter invalidates
  an earlier commit for that object;
- two distinct ordered RO observations after Save, with the sealed artifact SHA
  and exactly the intended object properties unchanged in both.

The SDK defines True as success and False as failure. This bounded object/layer
contract requires a successful own-object Update event **and** saved readback;
neither substitutes for the other. Known False-return exceptions for an identical
view restore are covered by the separate view-state oracle and are not generalized
to layer commits here. A layer False return needs separate native reconciliation.

The expected context key is collector-owned and explicit (for the reported hidden
view workflow, the committed system view zero). The oracle does not activate views,
assign Visible/Printable, call Update, save files or infer ownership. Reference or
UUID discovery, typed interface access, actual timing and the truth of reported
operations remain the exclusive native collector's responsibility.

Primary API reference supplied with the native observation:
[SDK 25 IDrawingObject.Update — update object data](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/idrawingobject_update.html).
The child-versus-parent persistence behavior is an observed native case modeled
synthetically here, not a claim that this page guarantees every descendant rule.
Root's corrected hidden-view **native two-RO check remains pending in this chat**;
no synthetic success is promoted to that acceptance. No engineering files,
product-specific values or output receipts are included in public fixtures.
