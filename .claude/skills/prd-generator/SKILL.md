---
name: prd-generator
description: Generate, critique, and refine PRDs, spec files, and roadmaps for initiative-level planning. Use to pressure-test and strengthen a PRD before planning. Triggers on "prd-generator", "prd generator".
tags:
  - documentation
  - planning
metadata:
  status: trial
---

# PRD Generator

## Philosophy

Framework-neutral. Present multiple applicable frameworks with tradeoffs, let the user choose.
Default to **critical feedback over validation**.

## Context

In the `tenon-begin-fast` pipeline this is Phase 4: refine and self-critique the `prd.md` that
`prd-interview` produced, then surface gaps before the review gate.

## Capabilities

| Capability | Trigger Phrases | Output |
|-----------|----------------|--------|
| **Critique PRDs/Specs** | "review my PRD", "what's missing" | Structured critique with severity ratings |
| **Generate PRDs** | "write a PRD for" | Complete PRD document |
| **Coach on Frameworks** | "how should I prioritize" | Framework comparison |
| **Review Roadmaps** | "review my roadmap" | Prioritization analysis |

## Workflow 1: Critique PRDs/Specs

Read the full document first. Score each dimension 🔴/🟡/🟢:

1. **Problem Definition**
2. **User Understanding**
3. **Success Metrics**
4. **Scope Clarity**
5. **Edge Cases & Risks**
6. **Stakeholder Alignment**
7. **Feasibility Signal**
8. **Proof Honesty** *(Tenon-specific)* — Does the work keep the user's own checks as the only
   thing that decides the proof level? Is `UNVERIFIED` used honestly when no acceptable proof
   ran? Does any PR state the level it actually reached, never implying "verified" when it only
   type-checked?

Identify the top 3 gaps. End with ONE pointed question the author probably hasn't considered.

## Workflow 2: Generate PRDs

Gather inputs. Select depth (Lightweight Brief / Standard PRD / Full Spec). Problem Statement →
Goals & Success Metrics → Users & Scenarios → Requirements → Technical Considerations (incl.
proof-contract impact) → Risks & Mitigations → Out of Scope.

Always include explicit assumptions, open questions, a Risks & Mitigations section. Reference
`R1`..`R8` and the capability (`T1`..`T11`).

Self-critique with Workflow 1 against your own output.

## Workflow 3: Coach on Frameworks

RICE, ICE, MoSCoW, Kano, Weighted Scoring, Cost of Delay/WSJF; JTBD, Opportunity Solution Trees;
Porter's Five Forces, Wardley Mapping; TAM/SAM/SOM, Fermi estimation.

## Workflow 4: Review Roadmaps & Prioritization

| Approach | Optimizes For | Tradeoff |
|----------|--------------|----------|
| **Impact-first** | Maximum outcome per unit time | May defer foundational work |
| **De-risk first** | Reduce uncertainty early | Slower visible progress |
| **Quick wins first** | Momentum | May delay strategic bets |
| **Dependencies-first** | Unblock parallel work | Front-loads less exciting work |

## Visual-First Preview

```
PRD: {slug}
├─ Problem ........... {one line}
├─ Goals/Metrics ..... {one line}
├─ Users/Scenarios ... {one line}
├─ Requirements ...... must:{n}  should:{n}  nice:{n}
├─ Technical ......... {proof-contract impact in a phrase}
├─ Risks ............. {top risk}
└─ Out of scope ...... {one line}
```

## Anti-Patterns (Never Do These)

1. Never just validate.
2. Never prescribe a single framework.
3. Never generate a PRD without flagging its own gaps.
4. Never give generic advice.
5. Never skip the hard question.
6. **Never wave through a PR that claims "verified" without stating the proof level it actually
   reached** — a model-proposed patch presented as fixed with no check run is a 🔴.
