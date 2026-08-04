# OpenRewrite Capability Summary

## Purpose

Compact description of what OpenRewrite can and cannot automate in DSARP.

## Can usually support

- rename class/method/package where exact entities are known,
- move class where package and imports can be safely updated,
- change package declarations,
- update imports,
- replace usages where exact types/methods are known,
- composite recipe plans.

## Should be recipe plan only

- dependency inversion requiring design choices,
- extract interface without exact method/member evidence,
- break cyclic dependency where edge direction is uncertain,
- package split/merge requiring architectural judgement,
- public API restructuring without compatibility analysis.

## Status labels

```text
draft
generated
validated
failed
not_applicable
```

## Validation requirements

Do not mark a recipe as `validated` unless dry run/build/tests/graph re-analysis passed as configured.
