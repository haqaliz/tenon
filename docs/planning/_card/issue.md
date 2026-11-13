# Card: feat/receiver-inference

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T12 Receiver tracking** — deeper slice: **typed-function inference** (T12c)
- **Milestone:** after v0.1.0/T10f; the receiver follow-up
- **State:** T12c shipped 2026-11-14 (`src/tenon/locate/*_scan.py`, same-file return annotations; 2,609 tests)
- **Branch:** `feat/receiver-inference/aliz`
- **Worktree:** `.claude/worktrees/feat-receiver-inference`

## Brief

T12a/T12b root a receiver from an explicit construction (`Client::new`, `new Client`, `Client()`), a
type annotation or a configured factory. A common style hides the construction behind a typed helper:

```python
def make_client() -> stripe.Client: ...
client = make_client()
client.charges.create(...)
```
```ts
function makeClient(): StripeClient { ... }
const client = makeClient();
client.charges.create({...})
```
```rust
fn make_client() -> Client { ... }
let client = make_client();
client.charges().create(...)
```
```go
func newClient() *stripe.Client { ... }
client := newClient()
client.Charges.New(...)
```
```csharp
static StripeClient MakeClient() => new(...);
var client = MakeClient();
client.Charges.Create(...);
```

T12c adds **typed-function inference**: a local function/method with an explicit SDK return
annotation (or, if chosen, a typed parameter) is evidence for the receiver/parameter's type. A call
assigned to a local roots the chain; only a written annotation/signature counts, never a bare
function name.

Parameter-type inference (a function parameter annotated with the SDK type is a rooted receiver
inside the body) is T12d if sliced.

The hard rules do not change: no unannotated-return guesses, no return-type analysis without a
signature, no new proof/ambiguity vocabulary, the shared policy decides.

## Constraints carried in from the repo

- T12a/T12b's receiver bindings and the five scanners are the base; extend, do not fork.
- The crate/package/namespace/import roots and alias resolution are reused for the return/parameter
  type.
- Stdlib/tree-sitter/`ast` only; offline fixtures/tests.
- `receivers`/`--receiver` remains the escape hatch for SDK factories whose return type is not in the
  repo.

## Scope fence

Not this card: unannotated return inference, SDK return types without an annotation/mapping,
package/repo-wide signature indexes unless chosen, generics, macros, `dynamic`/`getattr`, new proof
levels.
