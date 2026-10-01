"""Reproducible experiment drivers.

The measurements this project rests on -- eighteen planned moves across three repositories,
the Spoon/OpenRewrite agreement, the fifteen accepted patches -- were produced by scripts in a
temporary directory, with absolute paths to one machine's home folder. They were never
versioned, never tested, and would not survive the temp directory being cleared. That made the
central experiment unreproducible by anyone, including its author.

These modules are those drivers, with the paths taken from configuration or arguments and the
verdicts delegated to dsarp.verification.gates instead of re-derived per script.
"""
