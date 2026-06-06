# Harness CI/CD Lab — Retrospective & Golden-Path Pattern

A record of building an end-to-end Harness CI/CD pipeline for this PDF service
(**build → test → push image → canary deploy on Kubernetes**), what went wrong,
and — the part that actually matters — **how to templatize it so the next service
takes 20 minutes instead of a day.**

---

## 1. What we shipped

| Layer | Result |
|-------|--------|
| **App** | FastAPI PDF service (merge/split/compress/extract-text) |
| **Observability** | `/metrics` (Prometheus RED), JSON logs + request IDs, `/version` (baked git SHA), `/readyz` |
| **Supply chain** | digest-pinned base image, OCI provenance labels, build-arg provenance, `HEALTHCHECK` |
| **Deploy** | hardened Helm chart (non-root, read-only root FS, drop ALL caps, seccomp), split probes, PDB, optional HPA + ServiceMonitor |
| **CI gates** | Makefile + ruff/mypy/pytest, **25 tests / 96% coverage**, container smoke test |
| **Pipeline** | Harness CI (Kaniko build+push to `dtacci/pdf-service:<sha>`) → CD **Helm canary** to `pdf-pro-k8s` |
| **Proof** | `2/2` pods running, hardened; pod `/version` reports the same commit SHA it was built from → full **git → image → prod traceability** |

The application engineering needed essentially **zero rework**. All the pain was
in pipeline/connector configuration.

---

## 2. Where it hurt (ranked) — and the root cause of each

### 🥇 Built the wrong commit for hours — *the big one*
- **Symptom:** every build "succeeded" but produced the old skeleton (no `/version`, no labels).
- **Root cause:** the pipeline `codebase` block had a `repoName` but **no `connectorRef`**, so Harness silently fell back to a **hidden Harness-hosted Code repo** (the Get-Started skeleton), not GitHub.
- **Compounded by:** *Re-run* (replays the same commit) vs. a fresh *Run*.
- **Fix:** set `codebase.connectorRef` explicitly + move pipeline storage to GitHub.

### 🥈 The Service/manifest config gauntlet
A cascade of small, silent traps:
- Values override defaulting to `type: HarnessCode` (wrong repo → 404)
- Branch case sensitivity (`Main` ≠ `main`)
- A trailing space in a file path
- Duplicate manifest identifiers
- `connectorRef: __default__` (blank)
- Wrong manifest **type** (K8s Manifest vs Helm Chart)
- Entity file-path collision (Service tried to save to the *pipeline's* YAML path)

### 🥉 The final one-keystroke bug
- **Namespace** field set to the **connector name** (`pdfprocessork8scluster`) instead of `pdf-pro-k8s`. Everything else worked — it reached `kubectl apply` and died there.

### Smaller
- Docker connector creds (password reset), namespace didn't exist (`kubectl create ns`), and a dependency pin conflict (`prometheus-fastapi-instrumentator` 8.0.0 → 7.0.0 for Starlette compat).

### The pattern behind the pattern
**Every painful bug was the same class:** a Git/K8s reference silently pointing
at the wrong place (wrong repo, wrong branch, blank connector, wrong namespace),
with **no useful error until something downstream broke**. The platform defaults
to its own hidden repo and fails quietly. *That* is the thing to engineer away.

---

## 3. The Golden Path — templatizing this so it never hurts again

> Design goal: a new service onboards by filling in **one parameter file**.
> Everything else is generated from a template with **zero implicit defaults**,
> and a **pre-flight check** fails loudly *before* a build ever runs.

### Principle 1 — No implicit defaults
Every Git and K8s reference is an **explicit, required input**. No field is ever
left to "whatever the platform picks." This single rule kills the #1, #2, and 🥉
bugs above (hidden repo, `HarnessCode`, `__default__`, wrong namespace).

### Principle 2 — Declare each value once (single source of truth)
All the values that bit us live in **one** `service.config` and are *referenced*
everywhere else — never re-typed into a dozen UI fields where they drift.

```yaml
# deploy/harness/service.config.yaml  — the entire contract for a service
serviceName:     pdf-service
imageRepo:       dtacci/pdf-service
dockerConnector: pdfservice
gitConnector:    pdfprocessor
gitRepo:         pdf-processing-service
gitBranch:       main                    # lowercase, validated to exist
chartPath:       deploy/helm/pdf-service
valuesPath:      deploy/harness/values.yaml
k8sConnector:    pdfprocessork8scluster
namespace:       pdf-pro-k8s             # NOT the connector name
```

### Principle 3 — Parameterize, don't copy (Harness Pipeline Template)
Turn this pipeline into a reusable **Harness Pipeline/Stage Template**
(`templateRef`), with every connector/branch/namespace/path bound to a template
**input** — no hardcoded refs, no defaults. A new service = `templateRef` + the
config above. One template, N services, zero drift.

```
.harness/
  templates/
    cicd-canary-template.yaml   # CI build+push  +  CD Helm-canary, fully parameterized
  pdfprocesspipeline.yaml       # 10-line pipeline: templateRef + inputs from service.config
```

### Principle 4 — A scaffold (golden repo layout)
A new service starts from a cookiecutter-style scaffold so the *shape* is always
right and the hardened pieces come for free:

```
<service>/
  Dockerfile                     # multi-stage, digest-pinned, non-root, provenance ARGs
  deploy/helm/<service>/         # the hardened chart (probes, securityContext, PDB)
  deploy/harness/values.yaml     # image.tag: <+artifact.tag>   (deploy-time override)
  deploy/harness/service.config.yaml
  Makefile  pyproject.toml       # the CI gates
```

### Principle 5 — Fail loud, early (pre-flight check)
A validation step that runs **before** the build and encodes today's failure
modes, so a wrong ref is caught in seconds, not at minute-5 of `kubectl apply`:

```bash
# scripts/preflight.sh  — run as the first CI step (or a Make target)
# Asserts the exact things that silently broke us today:
- codebase.connectorRef is set and != __default__
- gitBranch is lowercase AND exists on the remote
- manifest store type == Github (never HarnessCode)
- namespace exists on the target cluster (and != the k8s connector name)
- no trailing whitespace in any path
- chart path contains a Chart.yaml; values path exists on the branch
```

### The payoff
| | Today (first time) | With the Golden Path |
|---|---|---|
| New service onboard | ~a day of config archaeology | edit `service.config` + `templateRef` |
| Where refs live | ~12 UI fields, drift-prone | 1 file, declared once |
| Wrong-ref failures | discovered minutes into a run | caught by pre-flight in seconds |
| Hardening / observability | hand-built | inherited from the scaffold |

**This is the actual deliverable.** The first pipeline is a one-off; the
*template + scaffold + pre-flight* is what makes it a repeatable, demoable
platform capability — and it directly neutralizes every class of bug in §2.
