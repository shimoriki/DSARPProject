@echo off
REM ===================================================================
REM  DSARP - Evidence-Based Refactoring Agent : one-click showcase
REM  Double-click this file, or run it from a terminal in the project.
REM  Press a key to advance between steps (you control the pacing).
REM
REM  SPLIT (current experiment):
REM    TRAINING     : 9 repos. Cassandra is ANT-based, so it is detected but
REM                   NOT refactorable - DSARP drives OpenRewrite through its
REM                   Maven and Gradle plugins only. Reported as
REM                   not_verifiable_unsupported_build, never as a clean result.
REM    UNSEEN TEST  : Apache Log4j2      - never trained on
REM    RANDOM TEST  : commons-validator  - small held-out repo
REM ===================================================================
setlocal
cd /d "%~dp0"
title DSARP Refactoring Agent - Showcase

where py >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python launcher "py" not found. Install Python 3.9+ first.
  pause
  exit /b 1
)

cls
echo ============================================================
echo    DSARP - Evidence-Based Refactoring Suggestion System
echo ============================================================
echo.
echo  This showcase will:
echo    1. Open the interactive dashboard in a new window
echo    2. Run the key demos here, step by step
echo    3. Finish with the REAL closed loop:
echo       Arcan + Designite  --^>  OpenRewrite  --^>  re-detect
echo.
echo  MODE:
echo    [F] FAST  (recommended for a live demo, ~5 min) - runs the tests and the
echo              short loop live, and SHOWS the recorded results for the long runs.
echo    [L] LIVE  (~40 min) - re-runs every measurement from scratch.
echo.
set "DSARP_FAST=1"
choice /C FL /N /M "  Press F for fast, L for live: "
if errorlevel 2 set "DSARP_FAST="
echo.

REM ---------- 1. Dashboard in its own window ----------
cls
echo [1/9] Launching the dashboard (opens in your web browser)...
echo       START on the "Presentation Summary" page - it is the whole MVP in one view:
echo       the 18.4%% attributable result, the per-smell-type breakdown, and the list of
echo       measurement traps the verification gate refuses to fall into.
echo       A new window will run the server; leave it open during the demo.
netstat -ano | findstr ":8501" >nul 2>&1
if not errorlevel 1 (
  echo       A dashboard is ALREADY running on http://localhost:8501 - reusing it
  echo       instead of starting a second copy on another port.
) else (
  start "DSARP Dashboard" cmd /k py -m streamlit run ui/streamlit_app.py
)
echo.
echo       Waiting a few seconds for the dashboard to start...
timeout /t 8 >nul
echo       If your browser did not open, go to the URL shown in the new window
echo       (usually http://localhost:8501).
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 2. Tests ----------
cls
echo [2/9] Proving the system is correct - running the test suite...
echo.
py -m pytest -q
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 3. Full pipeline demo ----------
cls
echo [3/9] End-to-end pipeline demo (offline, no cloud, no API keys)...
echo.
py -m dsarp.cli demo full
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 4. Live suggestions on the UNSEEN test repo ----------
cls
echo [4/9] Ranked, evidence-grounded suggestions for Apache Log4j2
echo       (the strictly held-out, UNSEEN test repository - never trained on)...
echo.
py -m dsarp.cli suggest --repo apache-logging-log4j2 --model offline --top-k 3
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 5. Works on ANY repo + leakage guard ----------
cls
echo [5/9] Inference on an unseen local Java repo (proves it is not hardcoded)...
echo.
py -m dsarp.cli evaluate --name mini-java --path data\samples\mini-java-repo --model offline
echo.
echo       Scientific-integrity check - Log4j2 is excluded from ALL training
echo       (Cassandra moved into training; Log4j2 is now the held-out benchmark):
py -m dsarp.cli evaluate apache-logging-log4j2 --dry-run
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 6. THE REAL CLOSED LOOP (headline result) ----------
cls
echo [6/9] REAL closed-loop verification - this is the core contribution.
echo.
echo       Both real tools run BEFORE and AFTER an actual refactoring:
echo         detect     Arcan 1.2.1 (package cycles, unstable, hub-like)
echo                    + DesigniteJava (class-level design smells)
echo         plan       derive concrete class moves that break the cycles
echo         refactor   OpenRewrite "mvn rewrite:run" rewrites the real source
echo         re-detect  run BOTH tools again on the refactored code
echo         compare    report exactly which smells were removed
echo         re-suggest generate NEW suggestions for the refactored code, so you
echo                    see what to do next - and what the refactoring introduced
echo.
echo       Running on commons-validator (this takes a few minutes)...
echo.
py -m dsarp.cli refactor-openrewrite --repo apache-commons-validator --detector both
echo.
echo       Full report: data\outputs\apache-commons-validator\openrewrite_loop_report.json
echo       The dashboard page "Refactoring Verification" shows the same
echo       before/after smell counts visually.
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 7. The verification gate - the core contribution ----------
cls
echo [7/9] The verification gate - why the numbers can be trusted.
echo.
echo       Every claim is measured, and measurement failures are never scored as
echo       success. Three real examples caught by this gate during development:
echo.
echo         - Arcan reported 20 smells -^> 0. FALSE: the refactored code had not
echo           compiled, so there was no bytecode to analyse. Now reported as
echo           UNMEASURABLE, and the run is marked unverified_build_broken.
echo         - An iterative run reported a 13.2%% reduction. FALSE: the build broke,
echo           Arcan dropped out, and the score was recomputed over fewer tools.
echo           Acceptance now also requires a COMPILING build.
echo         - An LLM proposed deleting a class its own reasoning said was still
echo           referenced. The closed loop returned verdict=rejected because the
echo           code did not compile.
echo.
echo       Each pass re-suggests against the refactored code, applies what is
echo       still safe, and re-detects. A pass is KEPT only if it compiles AND
echo       reduces the smells it targeted; anything else is rolled back.
echo.
if defined DSARP_FAST (
  echo       [FAST MODE] skipping the live 3-pass run; the per-type breakdown in the
  echo       next step is the same loop with attribution, and is shown from record.
) else (
  py -m dsarp.cli refactor-iterative --repo apache-commons-validator --detector both --max-passes 3
)
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 7b. One smell type per pass ----------
cls
echo [7b/9] Attributing the reduction to a SINGLE smell type.
echo.
echo       A mixed pass refactors several smell types at once, so when the count
echo       drops nothing says which type did it - and a type that quietly makes
echo       things worse hides behind the ones that help.
echo.
echo       --by-smell runs ONE type per pass, best measured record first:
echo         Cyclic Dependency -^> Unstable Dependency -^> Deficient Encapsulation
echo         -^> God Component -^> Scattered Functionality -^> Insufficient Modularization
echo.
echo       Re-detection happens between every pass, so each type works on a tree
echo       the earlier ones already improved. Types that CREATE structure before
echo       they pay off (God Component, Insufficient/Broken Modularization) get a
echo       consecutive second pass to consolidate. A type that does not help is
echo       rolled back and the run continues - that is the answer for that type,
echo       not a reason to abandon the rest.
echo.
if defined DSARP_FAST (
  echo       [FAST MODE] Showing the RECORDED result of this exact command.
  echo       Reproduced identically across three independent runs.
  echo.
  echo         pass  1   Cyclic Dependency            17 -^> 16   KEPT
  echo         pass 2-3  Unstable Dependency          build broke, rolled back
  echo         pass  4   Deficient Encapsulation      23 -^> 21   KEPT
  echo         pass  5   Deficient Encapsulation      21 -^> 20   KEPT
  echo         pass 6-7  Deficient Encapsulation      20 -^> 20   stopped, no longer paying
  echo         pass  8   God Component                 2 -^>  2   compiles, KEPT
  echo         pass 9-10 Scattered Functionality      build broke, rolled back
  echo         pass11-13 Insufficient Modularization   4 -^>  4   no effect, rolled back
  echo.
  echo         architectural smells 76 -^> 62   = 18.4%% reduction, 4 of 13 passes kept
  echo.
  echo       AND on a repository never seen before - apache/pdfbox, cloned and
  echo       measured from scratch:
  echo         Deficient Encapsulation  197 -^> 180 -^> 164 -^> 158  then stopped on its own
  echo         architectural smells 1782 -^> 1743  = 2.2%% reduction, 3 of 12 passes kept
) else (
  py -m dsarp.cli refactor-iterative --repo apache-commons-validator --detector both --by-smell
)
echo.
echo  See the "Presentation Summary" and "One smell type per pass" dashboard pages.
echo.
echo  Press a key for the next step...
pause >nul

REM ---------- 8. Supporting evidence: the learned ranker ----------
cls
echo [9/9] Supporting evidence - leave-one-repository-out generalization
echo       (gradient-boosted trees vs the grokking neural ranker).
echo       This ranks suggestions; it is an evaluation artifact, not part of the
echo       refactoring critical path.
echo.
if exist data\models\model_comparison.json (
  type data\models\model_comparison.json
) else (
  echo   [not found] run once first:  py scripts\sweep_neural_ranker.py
)
echo.
echo ============================================================
echo    Demo complete.
echo.
echo    To analyse ANY repository of your own:
echo      py -m dsarp.cli refactor-openrewrite --repo-url ^<git url^> --detector both
echo    ...or paste the git URL into the dashboard's "Analyze Repo" page.
echo.
echo    The dashboard is still open at http://localhost:8501
echo    Close its window (or press Ctrl+C there) to stop it.
echo ============================================================
echo.
pause >nul
endlocal
