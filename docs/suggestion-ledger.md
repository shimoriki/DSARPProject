# Per-suggestion ledger

Every recommendation in the three model CSVs, traced to how far it actually got.

Each number below comes from a run on this machine: the generator's own manifest for the
concrete stage, Maven for the build, and Arcan 1.2.1 for the measurement. A suggestion is
credited with improving its target only when the specific smell it named is absent
afterwards — not merely when the total fell.

## What one suggestion covers, and where its boundary is

| System | Rows | Distinct top labels | Smell types named | Median elements named |
|---|---|---|---|---|
| tika | 277 | Move Class (277) | Cyclic 261, Hub-like 13, Unstable 3 | 5 |
| log4j2 | 716 | Move Class (411), Move Attribute (305) | Cyclic 692, Hub-like 12, Unstable 12 | 9 |
| struts | 289 | Move Class (289) | Cyclic 281, Unstable 5, Hub-like 3 | 9 |

**What it contains.** A smell name, the elements it affects, and five refactoring *type*
names with scores.

**Where the boundary is.** It names no class to move and no destination to move it to.
Those parameters come from the repository's own `generate_recipes.py`, which infers them
from reciprocal package dependencies. So a suggestion constrains *what kind* of change to
make and *where to look*, never *what edit to perform*. Everything measured below is the
label plus the generator's inference, which is the only executable reading of it.

## Funnel

| Stage | Count | Of previous |
|---|---|---|
| sampled | 1282 | — |
| concrete | 473 | 36.9% |
| attempted | 354 | 74.8% |
| mechanical ok | 120 | 33.9% |
| comparable | 120 | 100.0% |
| target improved | 0 | 0.0% |
| regression free | 0 | — |

```
Resolution rate:                   473/1282  =  36.9%
Mechanical success rate:           120/354   =  33.9%
Target-smell improvement rate:       0/120   =   0.0%
Regression-free improvement rate:    0/120   =   0.0%
End-to-end success rate:             0/1282  =   0.0%
```

## Where recommendations stop, and why

| Stopped at | Count | Meaning |
|---|---|---|
| sampled | 809 | stopped at the label — no concrete change could be derived |
| concrete | 119 | a real change was derived, but it was never applied |
| attempted | 234 | applied, but the resulting tree was not measurable |
| comparable | 120 | measured, and the targeted smell survived |

### The commonest reasons, verbatim from the pipeline

| Reason | Count |
|---|---|
| screened out as unable to compile elsewhere, or never batched | 119 |
| target smell still present after the change | 117 |
| built 4 of the baseline's 24 modules; the counts are over different code | 71 |
| built 3 of the baseline's 41 modules; the counts are over different code | 49 |
| no direct reciprocal package dependency found | 46 |
| Move Class requires at least two affected packages | 31 |
| built 84 of the baseline's 101 modules; the counts are over different code | 25 |
| arcan did not run | 25 |

## Could the targeted smell be removed?

Of the **120** recommendations that reached a comparable measurement:

- the smell they named was present in the baseline for **117**
- it was still present afterwards for **118**
- it was removed for **0**

The three where the named smell was absent from the baseline are cases where the model
described a smell identity Arcan does not report at that revision.

This is a stronger statement than the headline deltas. Some batches did lower the total
count; none of them removed the particular cycle, hub or unstable dependency that the
suggestion was issued against. The reductions that did occur came from elsewhere in the
graph than the place the model pointed at.

## The recommendations that got furthest

All 120 that reached a comparable measurement, with the smell each targeted and its fate.

| # | System | Targeted smell | Elements | Class moved | Batch | Net | Target gone? |
|---|---|---|---|---|---|---|---|
| 2 | log4j2 | Cyclic | 4 | `LogLog` | log4j2-B1 | -16 | no |
| 3 | log4j2 | Cyclic | 3 | `AppenderAttachable` | log4j2-B2 | +27 | no |
| 4 | log4j2 | Cyclic | 5 | `ObjectRenderer` | log4j2-B1 | -16 | no |
| 5 | log4j2 | Cyclic | 3 | `RendererSupport` | log4j2-B1 | -16 | no |
| 14 | log4j2 | Cyclic | 2 | `GzCompressAction` | log4j2-B1 | -16 | no |
| 19 | log4j2 | Cyclic | 6 | `ZipCompressAction` | log4j2-B1 | -16 | no |
| 26 | log4j2 | Cyclic | 16 | `LoggerRepository` | log4j2-B1 | -16 | no |
| 29 | log4j2 | Cyclic | 3 | `PluginAttributeVisitor` | log4j2-B2 | +27 | no |
| 31 | log4j2 | Cyclic | 10 | `PluginVisitor` | log4j2-B3 | +19 | no |
| 33 | log4j2 | Cyclic | 4 | `PluginBuilderAttributeVisitor` | log4j2-B2 | +27 | no |
| 36 | log4j2 | Cyclic | 5 | `PluginConfigurationVisitor` | log4j2-B2 | +27 | no |
| 38 | log4j2 | Cyclic | 6 | `PluginElementVisitor` | log4j2-B2 | +27 | no |
| 43 | log4j2 | Cyclic | 6 | `NotBlankValidator` | log4j2-B1 | -16 | no |
| 44 | log4j2 | Cyclic | 5 | `RequiredValidator` | log4j2-B3 | +19 | no |
| 45 | log4j2 | Cyclic | 3 | `ValidHostValidator` | log4j2-B3 | +19 | no |
| 46 | log4j2 | Cyclic | 15 | `ValidPortValidator` | log4j2-B3 | +19 | no |
| 49 | log4j2 | Cyclic | 24 | `MessageFactory` | log4j2-B7 | -1 | no |
| 55 | log4j2 | Cyclic | 12 | `PluginLoggerContextVisitor` | log4j2-B2 | +27 | no |
| 60 | log4j2 | Cyclic | 13 | `PluginNodeVisitor` | log4j2-B2 | +27 | no |
| 65 | log4j2 | Cyclic | 14 | `PluginValueVisitor` | log4j2-B2 | +27 | no |
| 69 | log4j2 | Cyclic | 29 | `LogManagerStatus` | log4j2-B2 | +27 | no |
| 80 | log4j2 | Cyclic | 32 | `TestProvider` | log4j2-B1 | -16 | no |
| 84 | log4j2 | Cyclic | 21 | `ScriptRef` | log4j2-B3 | +19 | no |
| 89 | log4j2 | Cyclic | 26 | `ScriptManager` | log4j2-B3 | +19 | no |
| 92 | log4j2 | Cyclic | 28 | `ThreadContextDataInjector` | log4j2-B3 | +19 | no |
| 94 | log4j2 | Cyclic | 27 | `AbstractScript` | log4j2-B3 | +19 | no |
| 95 | log4j2 | Cyclic | 11 | `MultiFormatStringBuilderFormattable` | log4j2-B3 | +19 | no |
| 99 | log4j2 | Cyclic | 26 | `ArrayBlockingQueueFactory` | log4j2-B1 | -16 | no |
| 104 | log4j2 | Cyclic | 34 | `Advertiser` | log4j2-B3 | +19 | no |
| 120 | log4j2 | Cyclic | 14 | `SecurityManagerTestRule` | log4j2-B2 | +27 | no |
| 123 | log4j2 | Cyclic | 37 | `AbstractSerializationTest` | log4j2-B3 | +19 | no |
| 125 | log4j2 | Cyclic | 8 | `TestLoggerContext` | log4j2-B3 | +19 | no |
| 126 | log4j2 | Cyclic | 16 | `TestLoggerContextFactory` | log4j2-B3 | +19 | no |
| 130 | log4j2 | Cyclic | 28 | `DiscardingAsyncQueueFullPolicy` | log4j2-B2 | +27 | no |
| 131 | log4j2 | Cyclic | 35 | `LastModifiedSource` | log4j2-B2 | +27 | no |
| 132 | log4j2 | Cyclic | 28 | `HttpInputStreamUtil` | log4j2-B2 | +27 | no |
| 144 | log4j2 | Cyclic | 27 | `JndiRule` | log4j2-B3 | +19 | no |
| 149 | log4j2 | Cyclic | 29 | `LoggerFields` | log4j2-B3 | +19 | no |
| 152 | log4j2 | Cyclic | 23 | `JdbcRule` | log4j2-B2 | +27 | no |
| 156 | log4j2 | Cyclic | 37 | `ExtendedLevels` | log4j2-B2 | +27 | no |
| 157 | log4j2 | Cyclic | 30 | `GcFreeLoggingTestUtil` | log4j2-B3 | +19 | no |
| 162 | log4j2 | Cyclic | 31 | `FailOnceAppender` | log4j2-B2 | +27 | no |
| 163 | log4j2 | Cyclic | 30 | `BlockingAppender` | log4j2-B2 | +27 | no |
| 169 | log4j2 | Cyclic | 32 | `InMemoryAppender` | log4j2-B2 | +27 | no |
| 192 | log4j2 | Cyclic | 2 | `CompositeFilterComponentBuilder` | log4j2-B1 | -16 | no |
| 196 | log4j2 | Cyclic | 18 | `CustomLevelComponentBuilder` | log4j2-B1 | -16 | no |
| 197 | log4j2 | Cyclic | 13 | `KeyValuePairComponentBuilder` | log4j2-B1 | -16 | no |
| 215 | log4j2 | Cyclic | 35 | `BasicAsyncLoggerContextSelector` | log4j2-B2 | +27 | no |
| 223 | log4j2 | Cyclic | 28 | `PosixViewAttributeAction` | log4j2-B1 | -16 | no |
| 226 | log4j2 | Cyclic | 27 | `CompositeAction` | log4j2-B1 | -16 | no |
| 235 | log4j2 | Cyclic | 20 | `ThrowableFormatOptions` | log4j2-B3 | +19 | no |
| 248 | log4j2 | Cyclic | 26 | `DirectFileRolloverStrategy` | log4j2-B2 | +27 | no |
| 259 | log4j2 | Cyclic | 32 | `SimpleProvider` | log4j2-B2 | +27 | no |
| 268 | log4j2 | Cyclic | 8 | `FilteredObjectInputStream` | log4j2-B3 | +19 | no |
| 273 | log4j2 | Cyclic | 26 | `FilterAdapter` | log4j2-B1 | -16 | no |
| 274 | log4j2 | Cyclic | 19 | `RingBufferAdmin` | log4j2-B3 | +19 | no |
| 292 | log4j2 | Cyclic | 13 | `ExecutorServices` | log4j2-B3 | +19 | no |
| 294 | log4j2 | Cyclic | 12 | `Source` | log4j2-B11 *(alone)* | +14 | no |
| 304 | log4j2 | Cyclic | 7 | `ConfigurationFactoryData` | log4j2-B1 | -16 | no |
| 307 | log4j2 | Cyclic | 6 | `SelectArbiter` | log4j2-B2 | +27 | no |

… and 60 more, all with the same verdict.
