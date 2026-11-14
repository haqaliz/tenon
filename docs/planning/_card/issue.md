# Card: feat/parameter-inference

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T12 Receiver tracking** — deeper slice: **typed parameters** (T12d)
- **Milestone:** after T12c (annotated return types); the receiver follow-up
- **Branch:** `feat/parameter-inference/aliz`
- **Worktree:** `.claude/worktrees/feat-parameter-inference`

## Brief

T12c roots a receiver from a same-file helper's annotated **return** type. The other half is a typed
**parameter**: a function/method that receives the SDK client as an annotated argument.

```python
def create_charge(client: stripe.Client, amount: int):
    return client.charges.create(amount=amount)
```
```ts
function createCharge(client: StripeClient, amount: number) {
  return client.charges.create({ amount });
}
```
```rust
fn create_charge(client: &Client, amount: i64) {
    client.charges().create(amount);
}
```
```go
func createCharge(client *stripe.Client, amount int64) {
    client.Charges.New(params)
}
```
```csharp
static void CreateCharge(StripeClient client, long amount) {
    client.Charges.Create(options);
}
```

T12d adds **typed-parameter inference**: a parameter with an explicit SDK annotation/signature is a
rooted receiver inside that function/method body; the chain is `Type.member...` and the shared policy
decides certainty. Only a written parameter type counts; an unannotated parameter, `self`/`this`,
`any`/`void`, a generic or a non-SDK type is not evidence.

This completes the "deeper receiver inference" half (returns in T12c, parameters in T12d).

## Constraints carried in from the repo

- T12a–T12c's receiver bindings and the five scanners are the base; extend, do not fork.
- The crate/package/namespace/import roots and alias resolution are reused for the parameter type.
- The parameter binding is per function; a local assignment rebinds; a nested function's parameters
  are its own.
- Stdlib/tree-sitter/`ast` only; offline tests.

## Scope fence

Not this card: unannotated parameters, `self`/`this` method-return inference, generic/overload
resolution, cross-file/package indexes, new proof levels/ambiguity reasons, a service change.
