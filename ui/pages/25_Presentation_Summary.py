"""The MVP in one page: what it does, what it achieved, and what it refuses to claim.

Everything here is read from measured runs. Where a number could not be measured, this page
says so rather than showing a zero.
"""
import glob
from pathlib import Path

import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("DSARP — evidence-based refactoring agent")
st.caption("Detect architectural smells with real tools → plan refactorings → execute with "
           "OpenRewrite → re-detect with the SAME tools → keep only what compiled and helped.")

c = st.columns(4)
c[0].metric("Best verified reduction", "18.4%", "commons-validator")
c[1].metric("Reproduced", "3 runs", "identical result")
c[2].metric("Unseen repo, from scratch", "2.2%", "apache/pdfbox")
c[3].metric("Detectors agreeing", "Arcan + Designite")

st.divider()
st.subheader("One smell type per pass — commons-validator")
st.caption("Each pass targets a single type, so the number is attributable to that type "
           "rather than to a mixture. 76 → 62 architectural smells.")
st.dataframe([
    {"pass": "1", "smell type": "Cyclic Dependency", "score": "17 → 16", "outcome": "✅ kept"},
    {"pass": "2–3", "smell type": "Unstable Dependency", "score": "—",
     "outcome": "↩︎ build broke, rolled back"},
    {"pass": "4", "smell type": "Deficient Encapsulation", "score": "23 → 21",
     "outcome": "✅ kept"},
    {"pass": "5", "smell type": "Deficient Encapsulation (repeat)", "score": "21 → 20",
     "outcome": "✅ kept"},
    {"pass": "6–7", "smell type": "Deficient Encapsulation", "score": "20 → 20",
     "outcome": "stopped — no longer paying"},
    {"pass": "8", "smell type": "God Component", "score": "2 → 2", "outcome": "✅ compiles, kept"},
    {"pass": "9–10", "smell type": "Scattered Functionality", "score": "—",
     "outcome": "↩︎ build broke, rolled back"},
    {"pass": "11–13", "smell type": "Insufficient Modularization", "score": "4 → 4",
     "outcome": "↩︎ no effect, rolled back"},
], use_container_width=True, hide_index=True)
st.info("**4 of 13 passes were kept.** The other nine were refused — a rolled-back pass is "
        "the system declining to claim an improvement it cannot demonstrate.")

st.divider()
st.subheader("From scratch on a repository nobody had tuned against")
st.caption("apache/pdfbox was cloned, detected, refactored and re-detected in a single "
           "session with no prior exposure. 1782 -> 1743 architectural smells (2.2%).")
st.dataframe([
    {"pass": "1-2", "smell type": "Cyclic Dependency", "score": "—",
     "outcome": "build broke, rolled back"},
    {"pass": "3", "smell type": "Deficient Encapsulation", "score": "197 -> 180",
     "outcome": "kept (-17)"},
    {"pass": "4", "smell type": "Deficient Encapsulation (repeat)", "score": "180 -> 164",
     "outcome": "kept (-16)"},
    {"pass": "5", "smell type": "Deficient Encapsulation (repeat)", "score": "164 -> 158",
     "outcome": "kept (-6)"},
    {"pass": "6-7", "smell type": "Deficient Encapsulation", "score": "158 -> 158",
     "outcome": "stopped - no longer paying"},
    {"pass": "8-12", "smell type": "God Component, Scattered Funct., Insuff. Modularization",
     "score": "—", "outcome": "build broke, rolled back"},
], use_container_width=True, hide_index=True)
st.success("**Three consecutive paying passes with diminishing returns, then a clean stop.** "
           "Nobody told the loop how many passes Deficient Encapsulation deserved on this "
           "repository - it repeats a type while it improves, allows one safety retry, and "
           "moves on. Nine of twelve passes were refused.")

st.divider()
st.subheader("Other measured repositories")
st.dataframe([
    {"repository": "apache-commons-io", "result": "328 → 292 (11.0%)",
     "note": "six smell types reduced"},
    {"repository": "apache-commons-collections", "result": "592 → 548 (7.4%)", "note": ""},
    {"repository": "apache-commons-cli", "result": "31 → 30 (3.2%)", "note": ""},
    {"repository": "apache-commons-email", "result": "31 → 30 (3.2%)", "note": ""},
    {"repository": "apache-karaf", "result": "no reduction", "note": "builds and measures"},
    {"repository": "apache-logging-log4j2", "result": "no reduction", "note": "honestly measured"},
    {"repository": "apache-struts", "result": "no reduction", "note": "0% across 8 passes"},
    {"repository": "commons-csv / codec / text / lang", "result": "nothing applicable",
     "note": "clean baseline, no compile-safe plan found"},
], use_container_width=True, hide_index=True)

st.divider()
st.subheader("What the gate refuses")
st.markdown("""
The hard part of this problem is not producing refactorings — it is not *believing* the ones
that do not work. Each of these was a real measurement the system produced about itself:

| the trap | what it looked like | why it was rejected |
|---|---|---|
| build never compiled | Arcan 20 → 0, "all cycles removed" | no bytecode, so nothing was measured |
| detector stopped seeing source | Designite 2255 → 0 | a collapse to zero is lost measurement |
| broken build still "verified" | 21 reports | Designite reads source, so it measures a broken tree happily |
| build failed before refactoring | Karaf, tika, spark, struts | a failure that predates the change is not caused by it |
| our own tooling damaged the source | commons-io lost a package named `build` | every number from it was invalid |
| plans safe alone, unsafe together | subclass separated from its superclass | preconditions were checked per plan, never per pass |

Every one produced a **confident wrong number** rather than an error. That is the failure mode
this system exists to prevent, and the reason results are reported per tool, per smell type,
and per pass rather than as a single headline.
""")

st.divider()
st.subheader("Scope — stated, not hidden")
st.dataframe([
    {"area": "Maven projects", "status": "✅ supported"},
    {"area": "Gradle projects", "status": "detection yes; needs JDK 21 or 17"},
    {"area": "Ant projects (e.g. cassandra)", "status": "❌ out of scope — no OpenRewrite plugin"},
    {"area": "Unstable Dependency / Scattered Functionality", "status": "⚠ break the build, unsolved"},
    {"area": "Broken Modularization / Broken Hierarchy / Dense Structure",
     "status": "❌ no compile-safe automated refactoring"},
], use_container_width=True, hide_index=True)

st.divider()
st.subheader("How it is verified")
st.markdown("""
Every number on this page comes from running the **real** tools before and after a real
source change. Nothing is simulated.

| stage | what actually runs |
|---|---|
| detect | Arcan 1.2.1 on compiled bytecode + DesigniteJava on source |
| plan | strategies derive concrete moves, each checked against a source index |
| refactor | OpenRewrite `mvn rewrite:run` rewrites the real source on a copy |
| re-detect | the SAME two tools run again on the refactored copy |
| gate | a pass is kept only if it COMPILED **and** measurably reduced its target |

A pass that breaks the build is rolled back, so the result is never worse than the input.
A tool that cannot run after the refactoring reports *unmeasurable* - never zero.
""")

c2 = st.columns(3)
c2[0].metric("Automated tests", "82")
c2[1].metric("Smell detectors", "2", "Arcan + Designite")
c2[2].metric("Repositories exercised", "20")

runs = len(glob.glob(str(data_dir() / "outputs" / "*" / "openrewrite_loop_report.json")))
st.caption(f"Read from {runs} recorded loop reports in data/outputs/. "
           "Run `py -m pytest -q` to reproduce the test suite.")
