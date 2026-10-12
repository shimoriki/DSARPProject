# Arcan 1.2.1 on Apache commons-validator

Generated in this session, not reused from an earlier run.

| | |
|---|---|
| Repository | https://github.com/apache/commons-validator |
| Commit | `b9eff75` (shallow clone, default branch) |
| Build | `mvn compile`, BUILD SUCCESS, 73 source files, 88 class files |
| Detector | Arcan 1.2.1, `-p <target/classes> -all` |
| Total distinct smells | **18** |

## Smells found

| Smell | Count | File |
|---|---|---|
| Cyclic Dependency, package level | 3 | `packageCyclicDependencyTable.csv` |
| Cyclic Dependency, class level | 11 | `classCyclicDependencyTable.csv` |
| Unstable Dependency | 4 | `UD.csv` |
| Hub-Like Dependency | 0 | *no `HL.csv` written* |

Arcan only writes `HL.csv` when it detects at least one hub-like dependency, so its
absence here is a real finding rather than a missing file.

## The three files that carry the smells

Everything else is either a metrics table or an alternative projection of the cycle data:

1. `packageCyclicDependencyTable.csv` — membership matrix, one row per cycle, one column per
   package, `1` where that package belongs to the cycle.
2. `classCyclicDependencyTable.csv` — the same, at class level.
3. `UD.csv` — one row per (unstable package, correlated package) pair, with Martin instability
   for each.

## Everything written

| File | Bytes | What it is |
|---|---|---|
| `packageCyclicDependencyTable.csv` | 594 | package cycle membership — **smells** |
| `classCyclicDependencyTable.csv` | 10,524 | class cycle membership — **smells** |
| `UD.csv` | 526 | unstable dependencies — **smells** |
| `UD30.csv` | 345 | the same, filtered at 30% instability — a severity view, **not extra smells** |
| `packageCyclicDependencyMatrix.csv` | 1,713 | package-to-package dependency matrix |
| `classCyclicDependencyMatrix.csv` | 70,087 | class-to-class dependency matrix |
| `packageCyclesShapeTable.csv` | 80 | cycle shape classification (header only here) |
| `classCyclesShapeTable.csv` | 715 | cycle shape classification |
| `PM.csv` | 421 | package metrics — not smells |
| `CM.csv` | 6,387 | class metrics — not smells |

## Note on UD30

`UD30.csv` is `UD.csv` filtered at a 30% instability threshold. Both of its pairs are already
in `UD.csv`, so counting the two files together would report 6 unstable dependencies where
there are 4. The totals above are distinct counts.

## Note on the number 18

This is an *architectural* smell count from Arcan. It is not comparable with the 201 figure
recorded elsewhere in this project for commons-validator, which came from DesigniteJava and
counts *implementation* smells. Different detectors, different unit of analysis.
