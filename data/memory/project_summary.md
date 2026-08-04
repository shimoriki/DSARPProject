# Project Summary

## Project name

DSARP Evidence-Based Refactoring Agent

## Purpose

Generate ranked, evidence-based Java refactoring suggestions by combining:

- RefactoringMiner historical commit data,
- Arcan and Designite smell evidence,
- dependency graphs,
- deterministic candidate generation,
- local/HPC ranking models,
- LLM explanation agents,
- OpenRewrite recipe plans,
- human HGRS feedback.

## Current MVP target

Train on several Java repositories and test on unseen Apache Cassandra.

## Repository policy

Training repositories may include Apache Tika, Log4j2, Struts, Karaf, Lucene, Commons Lang, Commons Collections, Maven, Guava, JFreeChart, and Spring Framework.

Apache Cassandra is final unseen test only. Do not use Cassandra examples during training, prompt tuning, ranker training, LoRA training, or validation.

## Main pipeline

```text
Repository
→ RefactoringMiner mining
→ Arcan/Designite/graph evidence
→ normalized evidence cases
→ aligned smell-refactoring examples
→ candidate generation
→ ranking
→ LLM explanation
→ OpenRewrite recipe plan
→ human HGRS review
→ dataset/ranker update
```
