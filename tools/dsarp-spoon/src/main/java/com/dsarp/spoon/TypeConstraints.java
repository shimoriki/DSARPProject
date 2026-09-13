package com.dsarp.spoon;

import spoon.reflect.CtModel;
import spoon.reflect.code.CtAssignment;
import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtFieldAccess;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtReturn;
import spoon.reflect.code.CtVariableAccess;
import spoon.reflect.declaration.CtElement;
import spoon.reflect.declaration.CtExecutable;
import spoon.reflect.declaration.CtField;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtParameter;
import spoon.reflect.declaration.CtType;
import spoon.reflect.declaration.CtVariable;
import spoon.reflect.declaration.ModifierKind;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.filter.TypeFilter;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Which declarations of a type can be replaced by an interface, by type constraints.
 *
 * The checklist this replaces leaked four times, each found by a real build failure: a value
 * escaping through an invocation argument, through an assignment, through an overridden
 * return type, and a consumer package that subclassed the implementation. It was still
 * leaking on generic containers when it was retired. A checklist asks "does any bad usage
 * exist?" and refuses the whole candidate; every new escape route is a new special case, and
 * the routes are unbounded.
 *
 * Constraints ask a different question: WHICH DECLARATIONS can move? Following Tip, Kiezun and
 * Baeumer, each declaration of the type is a variable, assignments and argument passing and
 * returns are edges, declarations with a use the interface cannot satisfy are seeded as
 * concrete, and the seeds propagate. Whatever survives can be retargeted; the rest stays.
 *
 * Two properties fall out for free rather than needing rules:
 *
 *   Construction stops being a blocker. `Iface x = new Impl()` is perfectly legal Java, and
 *   the old checklist refused sixteen pdfbox candidates for it. Only the declaration's type
 *   changes; what is assigned into it does not have to.
 *
 *   Generic containers stop leaking. A `List&lt;Impl&gt;` declaration has type List, not Impl,
 *   so it is never a constraint variable and is never retargeted. That is exactly the CFFFont
 *   failure, fixed by the shape of the analysis instead of by a fifth rule.
 *
 * The direction that matters: for `a = b`, retargeting b forces retargeting a, because
 * assigning an interface into a slot still typed as the class does not compile. So blocking
 * propagates BACKWARDS, from destination to source.
 */
final class TypeConstraints {

    /** A declaration whose type is the implementation class: field, local, parameter, return. */
    static final class Slot {
        final CtElement decl;
        final String describe;
        Slot(CtElement decl, String describe) { this.decl = decl; this.describe = describe; }
    }

    static final class Result {
        /** Declarations that may become the interface. */
        final Set<CtElement> retargetable = new LinkedHashSet<>();
        /** Methods the interface has to declare, because a retargetable slot calls them. */
        final Set<CtMethod<?>> methods = new LinkedHashSet<>();
        /** Declarations that must stay concrete, and why. */
        final Map<String, String> blocked = new LinkedHashMap<>();
        int totalSlots;

        boolean anythingToDo() { return !retargetable.isEmpty() && !methods.isEmpty(); }
    }

    private TypeConstraints() {}

    static Result solve(CtModel model, CtType<?> impl, String consumerPkg) {
        final String self = impl.getQualifiedName();
        Result r = new Result();

        // ---- variables: every declaration in the consumer package typed exactly as impl ----
        Map<CtElement, Slot> slots = new IdentityHashMap<>();
        for (CtVariable<?> v : model.getElements(new TypeFilter<>(CtVariable.class))) {
            if (!isType(v.getType(), self)) continue;
            if (!inConsumer(v, consumerPkg)) continue;
            slots.put(v, new Slot(v, kind(v) + " " + v.getSimpleName()));
        }
        for (CtMethod<?> m : model.getElements(new TypeFilter<>(CtMethod.class))) {
            if (!isType(m.getType(), self)) continue;
            if (!inConsumer(m, consumerPkg)) continue;
            slots.put(m, new Slot(m, "return of " + m.getSimpleName() + "()"));
        }
        r.totalSlots = slots.size();
        if (slots.isEmpty()) return r;

        Set<CtElement> blocked = new LinkedHashSet<>();
        Map<CtElement, String> why = new IdentityHashMap<>();
        // dest -> sources, so blocking a destination can be pushed back to what feeds it
        Map<CtElement, Set<CtElement>> feeders = new IdentityHashMap<>();

        // ---- seeds: uses the interface cannot satisfy -------------------------------------
        for (CtFieldAccess<?> fa : model.getElements(new TypeFilter<>(CtFieldAccess.class))) {
            CtExpression<?> target = fa.getTarget();
            CtElement d = declOf(target);
            if (d != null && slots.containsKey(d) && fa.getVariable() != null
                && fa.getVariable().getDeclaringType() != null
                && self.equals(fa.getVariable().getDeclaringType().getQualifiedName())) {
                block(blocked, why, d, "reads field " + fa.getVariable().getSimpleName()
                                       + ", which an interface cannot declare");
            }
        }
        for (CtInvocation<?> inv : model.getElements(new TypeFilter<>(CtInvocation.class))) {
            CtExecutableReference<?> exe = inv.getExecutable();
            if (exe == null) continue;
            CtElement d = declOf(inv.getTarget());
            if (d != null && slots.containsKey(d) && exe.getDeclaringType() != null
                && self.equals(exe.getDeclaringType().getQualifiedName())) {
                Object decl = exe.getExecutableDeclaration();
                if (!(decl instanceof CtMethod)) {
                    block(blocked, why, d, "uses a non-method member");
                } else {
                    CtMethod<?> m = (CtMethod<?>) decl;
                    if (m.getModifiers().contains(ModifierKind.STATIC))
                        block(blocked, why, d, "calls static " + m.getSimpleName() + "()");
                    else if (!m.getModifiers().contains(ModifierKind.PUBLIC))
                        block(blocked, why, d, "calls non-public " + m.getSimpleName() + "()");
                }
            }
            // argument passing is assignment into the parameter
            List<CtExpression<?>> args = new ArrayList<>(inv.getArguments());
            Object ed = exe.getExecutableDeclaration();
            if (ed instanceof CtExecutable) {
                List<CtParameter<?>> ps = new ArrayList<>(((CtExecutable<?>) ed).getParameters());
                for (int i = 0; i < Math.min(args.size(), ps.size()); i++) {
                    CtElement src = declOf(args.get(i));
                    if (src == null || !slots.containsKey(src)) continue;
                    CtParameter<?> p = ps.get(i);
                    if (slots.containsKey(p)) {
                        feeders.computeIfAbsent(p, k -> new LinkedHashSet<>()).add(src);
                    } else if (isType(p.getType(), self)) {
                        // parameter typed as the class but outside the consumer package: it
                        // will still demand the class after we are done
                        block(blocked, why, src, "passed to " + exe.getSimpleName()
                                                 + "(), declared outside " + consumerPkg);
                    }
                }
            }
        }
        for (CtAssignment<?, ?> asg : model.getElements(new TypeFilter<>(CtAssignment.class))) {
            CtElement dst = declOf(asg.getAssigned());
            CtElement src = declOf(asg.getAssignment());
            if (src == null || !slots.containsKey(src)) continue;
            if (dst != null && slots.containsKey(dst)) {
                feeders.computeIfAbsent(dst, k -> new LinkedHashSet<>()).add(src);
            } else if (dst != null && isTypedAs(dst, self)) {
                block(blocked, why, src, "assigned into a slot outside " + consumerPkg
                                         + " that is still typed as the class");
            }
        }
        for (CtReturn<?> ret : model.getElements(new TypeFilter<>(CtReturn.class))) {
            CtElement src = declOf(ret.getReturnedExpression());
            if (src == null || !slots.containsKey(src)) continue;
            CtMethod<?> owner = ret.getParent(CtMethod.class);
            if (owner == null) continue;
            if (slots.containsKey(owner)) {
                feeders.computeIfAbsent(owner, k -> new LinkedHashSet<>()).add(src);
            } else if (isType(owner.getType(), self)) {
                block(blocked, why, src, "returned from " + owner.getSimpleName()
                                         + "(), whose return type stays the class");
            }
        }
        // an overriding method cannot widen its return type past what the supertype promises
        for (CtElement e : new ArrayList<>(slots.keySet())) {
            if (!(e instanceof CtMethod)) continue;
            CtMethod<?> m = (CtMethod<?>) e;
            for (CtMethod<?> sup : m.getTopDefinitions()) {
                if (sup != m && !inConsumer(sup, consumerPkg)) {
                    block(blocked, why, m, "overrides " + sup.getSimpleName()
                                           + "() declared outside " + consumerPkg);
                    break;
                }
            }
        }

        // ---- propagate: if a destination must stay concrete, so must everything feeding it -
        Deque<CtElement> work = new ArrayDeque<>(blocked);
        while (!work.isEmpty()) {
            CtElement dst = work.pop();
            for (CtElement src : feeders.getOrDefault(dst, Set.of())) {
                if (blocked.add(src)) {
                    why.put(src, "flows into " + describe(slots, dst) + ", which must stay concrete");
                    work.push(src);
                }
            }
        }

        // ---- result --------------------------------------------------------------------
        for (Map.Entry<CtElement, Slot> en : slots.entrySet()) {
            if (blocked.contains(en.getKey()))
                r.blocked.put(en.getValue().describe, why.getOrDefault(en.getKey(), "blocked"));
            else
                r.retargetable.add(en.getKey());
        }
        // the interface only needs what the surviving slots actually call
        for (CtInvocation<?> inv : model.getElements(new TypeFilter<>(CtInvocation.class))) {
            CtElement d = declOf(inv.getTarget());
            if (d == null || !r.retargetable.contains(d)) continue;
            CtExecutableReference<?> exe = inv.getExecutable();
            if (exe == null || exe.getDeclaringType() == null) continue;
            if (!self.equals(exe.getDeclaringType().getQualifiedName())) continue;
            Object decl = exe.getExecutableDeclaration();
            if (decl instanceof CtMethod) r.methods.add((CtMethod<?>) decl);
        }
        return r;
    }

    // ------------------------------------------------------------------ helpers --

    private static void block(Set<CtElement> blocked, Map<CtElement, String> why,
                              CtElement d, String reason) {
        if (blocked.add(d)) why.put(d, reason);
    }

    private static String describe(Map<CtElement, Slot> slots, CtElement e) {
        Slot s = slots.get(e);
        return s == null ? "a declaration" : s.describe;
    }

    private static boolean isType(CtTypeReference<?> ref, String fqn) {
        return ref != null && fqn.equals(ref.getQualifiedName());
    }

    private static boolean isTypedAs(CtElement e, String fqn) {
        if (e instanceof CtVariable) return isType(((CtVariable<?>) e).getType(), fqn);
        if (e instanceof CtMethod) return isType(((CtMethod<?>) e).getType(), fqn);
        return false;
    }

    private static boolean inConsumer(CtElement e, String pkg) {
        CtType<?> t = e instanceof CtType ? (CtType<?>) e : e.getParent(CtType.class);
        while (t != null && t.getDeclaringType() != null) t = t.getDeclaringType();
        return t != null && t.getPackage() != null
               && pkg.equals(t.getPackage().getQualifiedName());
    }

    private static String kind(CtVariable<?> v) {
        if (v instanceof CtField) return "field";
        if (v instanceof CtParameter) return "parameter";
        return "local";
    }

    /** The declaration an expression reads, when it reads one. */
    private static CtElement declOf(CtExpression<?> e) {
        if (e instanceof CtVariableAccess) {
            CtVariableAccess<?> va = (CtVariableAccess<?>) e;
            return va.getVariable() == null ? null : va.getVariable().getDeclaration();
        }
        if (e instanceof CtInvocation) {
            CtExecutableReference<?> ex = ((CtInvocation<?>) e).getExecutable();
            Object d = ex == null ? null : ex.getExecutableDeclaration();
            return d instanceof CtMethod ? (CtMethod<?>) d : null;
        }
        return null;
    }
}
