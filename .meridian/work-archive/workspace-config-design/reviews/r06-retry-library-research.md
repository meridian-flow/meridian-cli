# R06 Retry Library Research

## 1. Shortlist

### 1. `dishka` — scoped DI container, modern async/web integrations

Purpose: build object graph from providers, scopes, context data.

API shape if adopted:

```python
from dishka import Provider, Scope, make_container, provide


class LaunchProvider(Provider):
    scope = Scope.APP

    @provide
    def launch_factory(self) -> LaunchContextFactory:
        return LaunchContextFactory(
            policy_resolver=PolicyResolver(),
            permission_builder=PermissionBuilder(),
            env_builder=EnvBuilder(),
            spec_builder=SpecBuilder(),
            observer_registry=ObserverRegistry(),
        )


container = make_container(LaunchProvider())
factory = container.get(LaunchContextFactory)
ctx = factory.build(raw_request, driver=DriverKind.PRIMARY)
```

Complexity delta, rough: add maybe 20k-40k LOC transitive mental surface, delete maybe 150-300 LOC meridian bootstrap glue. Runtime deps look light. Real cost not package size, cost is new provider DSL plus scope semantics.

Where it wins:
- Modern project, active. GitHub topic page shows repo updated 2025-11-18. Releases in 2025 frequent. `1.7.0` alone had many contributors and many framework fixes.
- Scope model fits "primary / worker / app request" better than old-school singleton-only DI.
- Good if meridian wanted many nested constructors, web integrations, request-local resources.

Where it fails:
- Does not solve raw-input normalization. Still need one meridian-owned factory that accepts raw spawn input and returns testable `LaunchContext`.
- Pushes problem sideways: now need provider graph for policy resolution, permission pipeline, env build, command build, fork materialization, session observer registry.
- Scope/context magic bigger than problem. R06 shape is composition-root problem, not "deep graph needs auto-wiring" problem.
- Type-heavy. More moving parts around generics, scopes, providers, async containers. Bugs in recent issues around `typing.Self`, conditional activation, Litestar integration.

Maintenance signal:
- Repo: https://github.com/reagento/dishka
- Releases: https://github.com/reagento/dishka/releases
- Active 2025 releases. Many outside contributors in `1.5.0`, `1.6.0`, `1.7.0`.
- Open issues updated recently: https://github.com/reagento/dishka/issues/706 , https://github.com/reagento/dishka/issues/690 , https://github.com/reagento/dishka/issues/699
- Alternative closest in same space: `dependency-injector`, `rodi`, `di`.

Verdict on fit: best DI candidate if team insists on library. Still not subsystem-collapsing win. Use only if goal expands to "framework-grade app-wide DI", not just R06.

### 2. `dependency-injector` — mature classic DI container with providers and wiring

Purpose: declarative container, providers, config, resources, framework wiring.

API shape if adopted:

```python
from dependency_injector import containers, providers


class LaunchContainer(containers.DeclarativeContainer):
    policy_resolver = providers.Factory(PolicyResolver)
    permission_builder = providers.Factory(PermissionBuilder)
    env_builder = providers.Factory(EnvBuilder)
    spec_builder = providers.Factory(SpecBuilder)
    factory = providers.Factory(
        LaunchContextFactory,
        policy_resolver=policy_resolver,
        permission_builder=permission_builder,
        env_builder=env_builder,
        spec_builder=spec_builder,
    )


factory = LaunchContainer().factory()
ctx = factory.build(raw_request, driver=DriverKind.WORKER)
```

Complexity delta, rough: add maybe 50k-100k LOC effective surface, delete maybe 150-300 LOC local composition glue. Package bigger than others. PyPI source dist for old 4.38.0 already ~797 kB. No runtime deps shown on PyPI, but internal provider surface big.

Where it wins:
- Mature, very active, many releases in 2025. Strong docs. Battle-tested in web/service apps.
- Good if meridian wanted full container features: override in tests, lifecycle/resource providers, framework wiring, config providers.
- Easier than `dishka` for explicit container-as-object style.

Where it fails:
- Overkill for one composition root. Forces provider language on simple pipeline.
- Wiring/decorator path fights strict typing and method semantics more than manual DI.
- Does not solve core R06 bug. Still need raw DTO reshape because container cannot infer policy from already-resolved `PreparedSpawnPlan`.
- Real-world issue traffic shows edge bugs in config laziness, classmethod injection, scoped containers.

Maintenance signal:
- Repo: https://github.com/ets-labs/python-dependency-injector
- Releases: https://github.com/ets-labs/python-dependency-injector/releases
- PyPI history shows frequent 2025 releases through `4.48.x`: https://pypi.org/project/dependency-injector/
- Recent issues: https://github.com/ets-labs/python-dependency-injector/issues/954 , https://github.com/ets-labs/python-dependency-injector/issues/947 , https://github.com/ets-labs/python-dependency-injector/issues/912
- More contributors than small DI libs. Good maintenance, but higher surface area.

Verdict on fit: strongest maintenance story. Weakest simplicity story. Helps only if meridian chooses "app-wide container" as design principle. R06 alone not enough reason.

### 3. Manual composition root + pydantic discriminated unions/validators — no new DI library

Purpose: keep one explicit factory. Use pydantic only for raw input normalization and sum types.

API shape if adopted:

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class PrimaryInput(BaseModel):
    kind: Literal["primary"]
    prompt: str
    sandbox: str
    approval: str


class WorkerInput(BaseModel):
    kind: Literal["worker"]
    spawn_id: str
    prompt: str
    sandbox: str
    approval: str


class RawLaunchInput(BaseModel):
    request: PrimaryInput | WorkerInput = Field(discriminator="kind")

    @model_validator(mode="after")
    def validate_shape(self) -> "RawLaunchInput":
        return self


class LaunchContextFactory:
    def build(self, raw: RawLaunchInput) -> LaunchContext:
        ...
```

Complexity delta, rough: add near-zero new deps. Delete maybe 200-500 LOC split resolution glue plus fake "factory" indirection. Uses pydantic already in tree.

Where it wins:
- Direct hit on actual problem: normalize raw input once, compose once, test once.
- Behaviorally testable by construction. Factory takes raw input, returns output.
- Keeps pyright story simple. No decorator injection magic. DTOs explicit.
- Works with current stack: Python 3.12+, pydantic 2.12+, pytest, strict pyright.
- Lets driven harness dispatch stay small: explicit method call or `match`, maybe `singledispatch` if desired.

Where it fails:
- Not subsystem collapse by library. Team still owns pipeline code.
- Pydantic validators can normalize shape, but should not become whole composition engine. Side effects like fork materialization and session observation still belong in explicit stages, not validators.

Maintenance signal:
- Pydantic already dependency. Docs current for discriminated unions and validators.
- Discriminated unions: https://docs.pydantic.dev/latest/concepts/unions/
- Validators: https://docs.pydantic.dev/latest/concepts/validators/
- `validate_call` exists, but not needed for core shape: https://docs.pydantic.dev/latest/concepts/validation_decorator/

Verdict on fit: best fit for constraints. Not flashy. Solves exact block. Lowest total complexity.

## 2. Rejected Candidates

- `punq` — tiny and pleasant, but maintainer openly notes typing gap. Recent issues still about typing, factory resolution, packaging. Good for toy/manual DI, not enough gain for R06.
- `inject` — simplest global binder style, but global state and decorator injection poor fit for pyright strict and concurrent entrypoints. Issue history explicitly calls out pyright/mypy pain and async/context-manager rough edges.
- `returns` — solves typed error/effect flows, not composition-root shape. Adds monadic vocabulary and mypy-plugin gravity. Pyright-strict team gets less value than mypy-centric team.
- `attrs` + builders — strong data modeling tool, but meridian already pays for pydantic. Swapping DTO base does not solve split composition root. Better only if project wanted less validation, more plain objects.
- `functools.singledispatch` — fine for one axis dispatch on first arg type. Good small tool for adapter selection, not composition-root fix.
- `multipledispatch` — stale relative to stdlib option, old design center, no need for extra dep when stdlib `singledispatch` handles simple adapter dispatch.
- `immutables.Map` — useful if `LaunchContext` needed persistent structural sharing across many branches. Here carrier small, mostly write-once. Extra C-extension and Python 3.14 wheel issue for little gain.

## 3. Pattern Recommendations, No Library

Best-fit pattern name: single explicit composition root / bootstrap, plus normalized request DTO at boundary.

Why:
- R06 failure is split composition root. Drivers still compose because factory input already carries resolved policy outputs.
- Fix is not container. Fix is move from pre-composed `PreparedSpawnPlan` to raw launch request union that factory can legally own.
- Literature match exact enough: Cosmic Python "Dependency Injection (and Bootstrapping)" says when entrypoints do too much init, add bootstrap/composition root and keep defaults/overrides there.

Pattern shape:
1. Boundary adapters map CLI args / HTTP body / worker spec into one discriminated raw DTO.
2. One factory `build_launch_context(raw, runtime_deps)` runs explicit stages:
   - resolve policy
   - build permissions
   - build env
   - build command/spec
   - materialize fork if needed
   - attach session observer strategy
3. Drivers execute already-composed result. No policy work outside factory.
4. Behavioral tests hit factory directly with raw DTO.

Real Python ecosystem examples:
- Cosmic Python bootstrap pattern: https://www.cosmicpython.com/book/chapter_13_dependency_injection.html
- FastAPI uses dependency injection at request boundary with explicit `Depends`, not app-wide hidden composition root: https://fastapi.tiangolo.com/reference/dependencies/
- Litestar/Starlite uses boundary-scoped `Provide`, again request/handler side, not generic composition engine: https://docs.litestar.dev/1/usage/dependency-injection.html
- Django mostly does startup via settings/apps registry and explicit app config, not third-party DI container.
- Temporal Python SDK examples assemble client and worker explicitly in startup code, not via DI container: https://python.temporal.io/

What mature projects usually do:
- Frameworks with own DI (`fastapi`, `litestar`) keep it at framework boundary.
- General Python apps often use manual bootstrap/composition root.
- Library code keeps constructors explicit. Container magic lives at app edge, if anywhere.

## 4. Verdict

**roll-your-own-with-pattern**

Pattern: single explicit composition root with raw-input DTO reshape. Use existing `pydantic` for discriminated raw input models and validation. Optional small use of stdlib `singledispatch` for harness-observer strategy registration if that reads cleaner than `match`.

Why no library wins:
- No library found that solves "3 entry points share composition, must stay behaviorally testable from raw input, and driven adapters have different session-observation mechanics."
- DI containers solve object graph wiring. R06 block is earlier: input normalization and ownership boundary.
- Bringing container adds provider DSL, scope semantics, decorator/wiring failure modes, and typing friction while meridian still must own exact stage pipeline.
- Lowest total complexity comes from reshaping DTOs and making factory honest.

Rough adoption plan:
1. Replace or narrow `PreparedSpawnPlan` so factory takes raw request union plus runtime deps, not pre-resolved execution policy.
2. Keep composition explicit in `LaunchContextFactory`.
3. Put side effects in named stages, not validators.
4. Add behavioral factory tests around permission flags, env shape, fork ordering, observer wiring.
5. Drop rg-count CI as proof. Keep only as drift alarm if desired.

Fallback if team insists on library:
- Pick `dishka`, not because it solves R06, but because it is smaller and more modern than `dependency-injector` for scoped Python apps.
- Limit it to outer composition root only. Do not leak provider/wiring syntax through core domain.

## 5. Evidence

- Shared context brief on exact R06 failure:
  - /home/jimyao/gitrepos/meridian-cli/.meridian/work/workspace-config-design/prompts/r06-retry-context-brief.md
- Project Python/tooling constraints:
  - /home/jimyao/gitrepos/meridian-cli/pyproject.toml
- Dishka repo:
  - https://github.com/reagento/dishka
- Dishka releases:
  - https://github.com/reagento/dishka/releases
- Dishka docs/build activity:
  - https://app.readthedocs.org/projects/dishka/
- Dishka recent issues:
  - https://github.com/reagento/dishka/issues/706
  - https://github.com/reagento/dishka/issues/690
  - https://github.com/reagento/dishka/issues/699
- Dependency Injector repo:
  - https://github.com/ets-labs/python-dependency-injector
- Dependency Injector releases:
  - https://github.com/ets-labs/python-dependency-injector/releases
- Dependency Injector PyPI:
  - https://pypi.org/project/dependency-injector/
- Dependency Injector recent issues:
  - https://github.com/ets-labs/python-dependency-injector/issues/954
  - https://github.com/ets-labs/python-dependency-injector/issues/947
  - https://github.com/ets-labs/python-dependency-injector/issues/912
- Punq issue tracker:
  - https://github.com/bobthemighty/punq/issues/189
  - https://github.com/bobthemighty/punq/issues/206
  - https://github.com/bobthemighty/punq/issues/208
  - https://github.com/bobthemighty/punq/issues/213
- Inject PyPI:
  - https://pypi.org/project/inject/
- Inject issue tracker:
  - https://github.com/ivankorobkov/python-inject/issues/80
  - https://github.com/ivankorobkov/python-inject/issues/112
  - https://github.com/ivankorobkov/python-inject/issues/116
- Returns PyPI:
  - https://pypi.org/project/returns/
- Returns issue tracker:
  - https://github.com/dry-python/returns/issues/2365
  - https://github.com/dry-python/returns/issues/2191
  - https://github.com/dry-python/returns/issues/1361
- attrs typing docs:
  - https://www.attrs.org/en/21.3.0/types.html
- attrs PyPI:
  - https://pypi.org/project/attrs/
- attrs typing issues:
  - https://github.com/python-attrs/attrs/issues/795
  - https://github.com/python-attrs/attrs/issues/1360
  - https://github.com/python-attrs/attrs/issues/1361
- Pydantic validators:
  - https://docs.pydantic.dev/latest/concepts/validators/
- Pydantic dataclasses:
  - https://docs.pydantic.dev/2.3/usage/dataclasses/
- stdlib `singledispatch` docs:
  - https://docs.python.org/3/library/functools.html#functools.singledispatch
- `immutables` PyPI:
  - https://pypi.org/project/immutables/
- `immutables` recent issue:
  - https://github.com/MagicStack/immutables/issues/121
- `multipledispatch` PyPI:
  - https://pypi.org/project/multipledispatch/0.4.7/
- Cosmic Python bootstrap chapter:
  - https://www.cosmicpython.com/book/chapter_13_dependency_injection.html
- FastAPI dependency docs:
  - https://fastapi.tiangolo.com/reference/dependencies/
- Litestar dependency docs:
  - https://docs.litestar.dev/1/usage/dependency-injection.html
- Temporal Python SDK docs:
  - https://python.temporal.io/

Report path: `/home/jimyao/gitrepos/meridian-cli/.meridian/work/workspace-config-design/reviews/r06-retry-library-research.md`

Verdict: `roll-your-own-with-pattern`
