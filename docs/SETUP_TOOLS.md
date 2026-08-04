# Tool setup

The external analysis tools are **not committed** — they are large third-party binaries, and
DesigniteJava Professional is licensed commercial software that may not be redistributed.
Install them locally into `tools/` before running the closed loop.

DSARP degrades honestly: any tool that is missing is reported as unavailable, and its smell
counts are recorded as `unmeasurable` rather than zero.

## Expected layout

```
tools/
  DesigniteJava.jar                      # Designite (Professional or community)
  arcan-1.2.1/distribution/arcan-1.2.1/  # FULL Arcan distribution: jar + lib/
  apache-maven-3.9.9/                    # or use Maven from PATH
  RefactoringMiner-3.1.4/                # optional, only for history mining
  dsarp-recipes/                         # committed — DSARP's own recipe module
```

## Arcan 1.2.1

Download the full distribution, not the bare jar — `arcan-1.2.1.jar` alone is a thin jar and
fails with `NoClassDefFoundError: tinkerpop/gremlin`. DSARP looks for an `arcan-*.jar` sitting
next to a non-empty `lib/` directory and ignores anything else.

Arcan analyses **compiled bytecode**, so DSARP runs `mvn compile` first and points Arcan at
`target/classes`.

```
java -jar arcan-1.2.1.jar -p <classes dir> -out <output dir> -all
```

Detects: Cyclic Dependency (package and class level), Unstable Dependency, Hub-Like Dependency.

## DesigniteJava

Get it from <https://www.designite-tools.com/>. The **Professional** edition writes
`ArchitectureSmells.csv` (God Component, Unstable Dependency, Cyclic Dependency, Scattered
Functionality) plus `DesignSmells.csv`; the free/community edition writes only
`designCodeSmells.csv`. DSARP reads whichever is present.

```
java -jar DesigniteJava.jar -i <repo> -o <output dir>
```

> Professional refuses to run when the output directory is not empty
> (`The specified output folder is not empty. Quitting..`). DSARP clears the directory before
> every run, so a stale run can never silently block a later one.

## Maven

Either put `mvn` on `PATH` or unpack a distribution to `tools/apache-maven-*/`. Maven drives
both `mvn compile` (for Arcan) and `mvn rewrite:run` (the actual refactoring).

## DSARP custom recipes (committed)

`tools/dsarp-recipes/` is our own source and **is** in the repository. Build it once:

```bash
mvn -f tools/dsarp-recipes/pom.xml install
```

That installs `com.dsarp:dsarp-recipes:1.0.0` into your local `~/.m2`, which DSARP passes to
Maven as `-Drewrite.recipeArtifactCoordinates`. It supplies two transformations stock
OpenRewrite cannot express declaratively:

| recipe | fixes | why it is needed |
|---|---|---|
| `ReduceFieldVisibility` | Deficient Encapsulation | `rewrite-java` has `ChangeMethodAccessLevel` but no field equivalent |
| `ExtractInterfaceForClass` | Rebellious Hierarchy, dependency inversion | wraps `ExtractInterface.CreateInterface`, which ships as a visitor and cannot be named in `rewrite.yml` |

## Verify

```bash
py -m dsarp.cli refactor-openrewrite --repo-url https://github.com/apache/commons-validator --detector both
```

The **How It Works** dashboard page shows which tools are runnable on the current machine.
