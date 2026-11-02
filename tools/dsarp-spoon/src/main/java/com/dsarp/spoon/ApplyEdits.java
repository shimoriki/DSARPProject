package com.dsarp.spoon;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import spoon.Launcher;
import spoon.reflect.CtModel;
import spoon.reflect.declaration.CtCompilationUnit;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtPackage;
import spoon.reflect.declaration.CtType;
import spoon.reflect.declaration.ModifierKind;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtFieldReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.filter.TypeFilter;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

/**
 * Applies a validated edit plan to Java source with Spoon.
 *
 * <pre>java -jar dsarp-spoon.jar &lt;repoRoot&gt; &lt;plan.json&gt; &lt;result.json&gt;</pre>
 *
 * The plan is produced by a model and validated in Python against an op allowlist before it
 * ever reaches here, so this class does no judgement of its own: it resolves, applies,
 * prints, and reports honestly what it could not do. An edit it cannot apply is reported as
 * skipped, never silently dropped -- "the run succeeded and changed nothing" has to be
 * distinguishable from "the run applied everything".
 *
 * Each source root gets its own Spoon model. That is both faster than one model of a 30
 * module repo and the reason cross-module moves are impossible here: a type can only be
 * moved within the root it was parsed from, which is exactly the safe subset.
 */
public final class ApplyEdits {

    public static void main(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println("usage: ApplyEdits <repoRoot> <plan.json> <result.json>");
            System.exit(2);
        }
        Path repo = Paths.get(args[0]).toAbsolutePath().normalize();
        ObjectMapper om = new ObjectMapper();
        JsonNode plan = om.readTree(new File(args[1]));

        List<JsonNode> pending = new ArrayList<>();
        for (JsonNode e : plan.withArray("edits")) pending.add(e);

        ObjectNode result = om.createObjectNode();
        ArrayNode applied = result.putArray("applied");
        ArrayNode skipped = result.putArray("skipped");
        ArrayNode changed = result.putArray("changedFiles");

        List<String> cp = new ArrayList<>();
        for (JsonNode c : plan.withArray("classpath")) cp.add(c.asText());
        String[] classpath = cp.toArray(new String[0]);
        // Spoon's JDT parser defaults to Java 8. tika-core is Java 17 and would not model at
        // all: "Syntax error on token implements, throws expected" — a parser set older than
        // the source, surfacing as if every candidate type were missing.
        int compliance = plan.path("complianceLevel").asInt(17);
        result.put("complianceLevel", compliance);
        result.put("classpathEntries", classpath.length);
        result.put("typeResolution", classpath.length > 0 ? "full" : "noClasspath");

        Path outDir = Paths.get(plan.path("outputDir").asText(
                repo.resolve("target/dsarp-spoon-out").toString()));
        Files.createDirectories(outDir);
        result.put("outputDir", outDir.toString());
        // precheck: decide legality only. Enumeration in Python cannot see package-private
        // field access, so it offered ten candidates on pdfbox that the model then spent ten
        // calls on and this driver refused all ten. Deciding first means the agent only ever
        // chooses between moves that can actually be applied.
        boolean precheckOnly = "precheck".equals(plan.path("mode").asText(""));
        conservative = plan.path("conservative").asBoolean(conservative);
        useConstraints = plan.path("constraints").asBoolean(useConstraints);
        result.put("constraints", useConstraints);
        result.put("conservative", conservative);
        for (Path root : sourceRoots(repo, plan)) {
            if (pending.isEmpty()) break;
            if (precheckOnly) precheckInRoot(root, classpath, compliance, pending, applied, skipped);
            else applyInRoot(root, outDir, classpath, compliance, pending, applied, skipped, changed, om);
        }
        result.put("mode", precheckOnly ? "precheck" : "apply");
        for (JsonNode e : pending) {
            ObjectNode s = skipped.addObject();
            s.set("edit", e);
            s.put("why", "type not found in any source root");
        }
        result.put("ok", skipped.isEmpty());
        om.writerWithDefaultPrettyPrinter().writeValue(new File(args[2]), result);
        System.out.println("applied=" + applied.size() + " skipped=" + skipped.size());
    }

    /** Explicit roots from the plan, else every module's src/main/java, else the repo. */
    private static List<Path> sourceRoots(Path repo, JsonNode plan) throws IOException {
        List<Path> roots = new ArrayList<>();
        for (JsonNode r : plan.withArray("sourceRoots")) roots.add(repo.resolve(r.asText()));
        if (!roots.isEmpty()) return roots;
        try (Stream<Path> s = Files.walk(repo, 4)) {
            s.filter(Files::isDirectory)
             .filter(p -> p.endsWith(Paths.get("src", "main", "java")))
             .forEach(roots::add);
        }
        if (roots.isEmpty()) roots.add(repo);
        return roots;
    }

    /**
     * Same-package types this one cannot be separated from.
     *
     * Every pdfbox refusal was of the form "uses field statusObj, not visible outside
     * org.apache.pdfbox.debugger.treestatus" — a class using a package-private member of a
     * neighbour. Moving the class alone is illegal; moving it TOGETHER WITH that neighbour
     * is not, because they land in the same package again. A candidate that is always
     * exactly one class can never express that, so the whole repository looked unrefactorable.
     */
    /** Same type, or one of its nested types — which travel with it. */
    private static boolean isSelf(String self, String other) {
        return other != null
               && (other.equals(self) || other.startsWith(self + "$") || other.startsWith(self + "."));
    }

    static java.util.Set<String> companions(CtType<?> type) {
        java.util.Set<String> out = new java.util.LinkedHashSet<>();
        String from = type.getPackage() == null ? "" : type.getPackage().getQualifiedName();

        for (CtTypeReference<?> ref : type.getElements(new TypeFilter<>(CtTypeReference.class))) {
            CtType<?> d = ref.getTypeDeclaration();
            if (d == null || d.getPackage() == null) continue;
            if (!from.equals(d.getPackage().getQualifiedName())) continue;
            if (d.getQualifiedName().equals(type.getQualifiedName())) continue;
            if (!d.getModifiers().contains(ModifierKind.PUBLIC)) out.add(d.getQualifiedName());
        }
        for (CtFieldReference<?> ref : type.getElements(new TypeFilter<>(CtFieldReference.class))) {
            if (ref.getFieldDeclaration() == null || ref.getDeclaringType() == null) continue;
            CtType<?> d = ref.getDeclaringType().getTypeDeclaration();
            if (d == null || d.getPackage() == null) continue;
            if (!from.equals(d.getPackage().getQualifiedName())) continue;
            if (isSelf(type.getQualifiedName(), d.getQualifiedName())) continue;
            java.util.Set<ModifierKind> m = ref.getFieldDeclaration().getModifiers();
            if (!m.contains(ModifierKind.PUBLIC) && !m.contains(ModifierKind.PROTECTED))
                out.add(d.getQualifiedName());
        }
        for (CtExecutableReference<?> ref : type.getElements(new TypeFilter<>(CtExecutableReference.class))) {
            if (ref.getExecutableDeclaration() == null || ref.getDeclaringType() == null) continue;
            CtType<?> d = ref.getDeclaringType().getTypeDeclaration();
            if (d == null || d.getPackage() == null) continue;
            if (!from.equals(d.getPackage().getQualifiedName())) continue;
            if (d.getQualifiedName().equals(type.getQualifiedName())) continue;
            if (!(ref.getExecutableDeclaration() instanceof spoon.reflect.declaration.CtModifiable)) continue;
            java.util.Set<ModifierKind> m =
                ((spoon.reflect.declaration.CtModifiable) ref.getExecutableDeclaration()).getModifiers();
            if (!m.contains(ModifierKind.PUBLIC) && !m.contains(ModifierKind.PROTECTED))
                out.add(d.getQualifiedName());
        }
        // A non-public type is also depended ON by its package: those users must come too.
        if (!type.getModifiers().contains(ModifierKind.PUBLIC)) {
            for (CtTypeReference<?> ref :
                    type.getFactory().getModel().getElements(new TypeFilter<>(CtTypeReference.class))) {
                if (!type.getQualifiedName().equals(ref.getQualifiedName())) continue;
                CtType<?> user = ref.getParent(CtType.class);
                if (user == null || user.getPackage() == null) continue;
                if (!from.equals(user.getPackage().getQualifiedName())) continue;
                if (!user.getQualifiedName().equals(type.getQualifiedName()))
                    out.add(user.getQualifiedName());
            }
        }
        out.remove(type.getQualifiedName());
        return out;
    }

    /**
     * Why this move is illegal, or null.
     *
     * Asks the resolved model rather than pattern-matching source. Two directions, both of
     * which produced real compile failures when they were not checked: what the moving type
     * needs from the package it is leaving, and what that package still needs from it.
     */
    private static String illegalReason(CtType<?> type, String toPackage) {
        return illegalReason(type, toPackage, java.util.Collections.emptySet());
    }

    /**
     * `alsoMoving` are types travelling with this one to the same package. A reference to
     * one of them is not a blocker: after the move they are neighbours again. Without this,
     * a group move is judged as if each class went alone, and every group is refused.
     */
    private static String illegalReason(CtType<?> type, String toPackage,
                                        java.util.Set<String> alsoMoving) {
        // A type carries its own members wherever it goes, nested types included. Counting
        // self-access as a blocker refused every candidate in pdfbox (0 legal of 14) — the
        // first refusal was TreeStatusPane "using" its own field statusObj.
        final String self = type.getQualifiedName();
        String from = type.getPackage() == null ? "" : type.getPackage().getQualifiedName();

        // The type is not public, so nothing outside its package can see it once it moves.
        if (!type.getModifiers().contains(ModifierKind.PUBLIC)) {
            for (CtTypeReference<?> ref :
                    type.getFactory().getModel().getElements(new TypeFilter<>(CtTypeReference.class))) {
                if (!type.getQualifiedName().equals(ref.getQualifiedName())) continue;
                CtType<?> user = ref.getParent(CtType.class);
                if (user == null || user.getPackage() == null) continue;
                String userPkg = user.getPackage().getQualifiedName();
                if (alsoMoving.contains(user.getQualifiedName())) continue;
                if (!userPkg.equals(toPackage) && !user.getQualifiedName().equals(type.getQualifiedName()))
                    return type.getSimpleName() + " is not public and " + user.getSimpleName()
                           + " in " + userPkg + " uses it";
            }
        }

        // Its OWN members may be non-public, and the package it leaves still uses them.
        // pdfbox: Stream moved out of debugger.streampane while StreamPane, left behind,
        // calls Stream's package-private constructor —
        // "Stream(COSStream,boolean) is not public in ...debugger.Stream". The type being
        // public is not enough; each member it exposes to its old neighbours must be too.
        for (CtExecutableReference<?> ref :
                type.getFactory().getModel().getElements(new TypeFilter<>(CtExecutableReference.class))) {
            if (ref.getDeclaringType() == null) continue;
            if (!self.equals(ref.getDeclaringType().getQualifiedName())) continue;
            Object decl = ref.getExecutableDeclaration();
            if (!(decl instanceof spoon.reflect.declaration.CtModifiable)) continue;
            java.util.Set<ModifierKind> mm =
                ((spoon.reflect.declaration.CtModifiable) decl).getModifiers();
            if (mm.contains(ModifierKind.PUBLIC) || mm.contains(ModifierKind.PROTECTED)) continue;
            CtType<?> user = ref.getParent(CtType.class);
            if (user == null || user.getPackage() == null) continue;
            if (isSelf(self, user.getQualifiedName())) continue;
            if (alsoMoving.contains(user.getQualifiedName())) continue;
            String userPkg = user.getPackage().getQualifiedName();
            if (userPkg.equals(from) && !userPkg.equals(toPackage))
                return user.getSimpleName() + " in " + from + " uses "
                       + type.getSimpleName() + "." + ref.getSimpleName()
                       + "(), which is not public";
        }
        for (CtFieldReference<?> ref :
                type.getFactory().getModel().getElements(new TypeFilter<>(CtFieldReference.class))) {
            if (ref.getDeclaringType() == null || ref.getFieldDeclaration() == null) continue;
            if (!self.equals(ref.getDeclaringType().getQualifiedName())) continue;
            java.util.Set<ModifierKind> mm = ref.getFieldDeclaration().getModifiers();
            if (mm.contains(ModifierKind.PUBLIC) || mm.contains(ModifierKind.PROTECTED)) continue;
            CtType<?> user = ref.getParent(CtType.class);
            if (user == null || user.getPackage() == null) continue;
            if (isSelf(self, user.getQualifiedName())) continue;
            if (alsoMoving.contains(user.getQualifiedName())) continue;
            String userPkg = user.getPackage().getQualifiedName();
            if (userPkg.equals(from) && !userPkg.equals(toPackage))
                return user.getSimpleName() + " in " + from + " uses field "
                       + type.getSimpleName() + "." + ref.getSimpleName()
                       + ", which is not public";
        }

        // The type uses something in its current package that it will no longer see.
        for (CtTypeReference<?> ref : type.getElements(new TypeFilter<>(CtTypeReference.class))) {
            CtType<?> decl = ref.getTypeDeclaration();
            if (decl == null || decl.getPackage() == null) continue;
            if (!from.equals(decl.getPackage().getQualifiedName())) continue;
            if (isSelf(self, decl.getQualifiedName())) continue;
            if (alsoMoving.contains(decl.getQualifiedName())) continue;
            if (!decl.getModifiers().contains(ModifierKind.PUBLIC))
                return "uses " + decl.getSimpleName() + ", which is not public in " + from;
        }
        for (CtFieldReference<?> ref : type.getElements(new TypeFilter<>(CtFieldReference.class))) {
            if (ref.getFieldDeclaration() == null || ref.getDeclaringType() == null) continue;
            if (ref.getDeclaringType().getPackage() == null) continue;
            if (!from.equals(ref.getDeclaringType().getPackage().getQualifiedName())) continue;
            if (alsoMoving.contains(ref.getDeclaringType().getQualifiedName())) continue;
            if (isSelf(self, ref.getDeclaringType().getQualifiedName())) continue;
            java.util.Set<ModifierKind> m = ref.getFieldDeclaration().getModifiers();
            if (!m.contains(ModifierKind.PUBLIC) && !m.contains(ModifierKind.PROTECTED))
                return "uses field " + ref.getSimpleName() + ", not visible outside " + from;
        }
        for (CtExecutableReference<?> ref : type.getElements(new TypeFilter<>(CtExecutableReference.class))) {
            if (ref.getExecutableDeclaration() == null || ref.getDeclaringType() == null) continue;
            if (ref.getDeclaringType().getPackage() == null) continue;
            if (!from.equals(ref.getDeclaringType().getPackage().getQualifiedName())) continue;
            if (alsoMoving.contains(ref.getDeclaringType().getQualifiedName())) continue;
            if (isSelf(self, ref.getDeclaringType().getQualifiedName())) continue;
            if (!(ref.getExecutableDeclaration() instanceof spoon.reflect.declaration.CtModifiable)) continue;
            java.util.Set<ModifierKind> m =
                ((spoon.reflect.declaration.CtModifiable) ref.getExecutableDeclaration()).getModifiers();
            if (!m.contains(ModifierKind.PUBLIC) && !m.contains(ModifierKind.PROTECTED))
                return "uses member " + ref.getSimpleName() + "(), not visible outside " + from;
        }
        return null;
    }

    /**
     * A configured Launcher over `root`, optionally with the module's test sources too.
     *
     * The test root is derived from the layout (src/main/java -> src/test/java) rather than
     * passed in, so a caller cannot forget it and quietly get the weaker check back.
     */
    private static Launcher newLauncher(Path root, String[] classpath, int compliance,
                                        boolean includeTests) {
        Launcher launcher = new Launcher();
        launcher.addInputResource(root.toString());
        if (includeTests) {
            Path src = root.getParent() == null ? null : root.getParent().getParent();
            if (src != null) {
                Path testRoot = src.resolve("test").resolve("java");
                if (Files.isDirectory(testRoot)) launcher.addInputResource(testRoot.toString());
            }
        }
        launcher.getEnvironment().setCommentEnabled(true);
        launcher.getEnvironment().setComplianceLevel(compliance);
        // One unparseable file must not cost the whole module. log4j-core returned
        // "Syntax error, modifiers are not allowed here" on
        // org/apache/logging/log4j/core/util/datetime/package-info.java:23, and that single
        // file sank the model build for all 40 inversion candidates in the module — reported
        // as 0 legal, which reads like a fact about log4j2's cycles and is a fact about a
        // package annotation. package-info.java declares no type we can refactor, so nothing
        // we decide depends on parsing it.
        launcher.getEnvironment().setIgnoreSyntaxErrors(true);
        if (classpath.length > 0) {
            launcher.getEnvironment().setNoClasspath(false);
            launcher.getEnvironment().setSourceClasspath(classpath);
        } else {
            launcher.getEnvironment().setNoClasspath(true);
        }
        return launcher;
    }

    /** Report which candidate moves are legal in this root, changing nothing. */
    private static void precheckInRoot(Path root, String[] classpath, int compliance,
                                       List<JsonNode> pending,
                                       ArrayNode legal, ArrayNode illegal) {
        if (!Files.isDirectory(root)) return;
        List<JsonNode> candidates = new ArrayList<>();
        for (JsonNode e : pending) if (hasFileFor(root, e.path("type").asText())) candidates.add(e);
        if (candidates.isEmpty()) return;

        // Test sources have to be IN the model. Without them a move that breaks only tests is
        // reported legal: commons-validator's ISBNValidator moved routines ->
        // routines.checkdigit, main source compiled cleanly, and ISBNValidatorTest -- left
        // behind in routines -- reads its package-private ISBN10_REGEX. The precheck said
        // legal and the build said "cannot be accessed from outside package". illegalReason
        // already scans the whole model and its userPkg.equals(from) test would have caught
        // it; the test file was simply never parsed.
        Launcher launcher = newLauncher(root, classpath, compliance, true);
        boolean testsModelled = true;
        Throwable failure = null;
        try {
            launcher.buildModel();
        } catch (Throwable t) {
            // Test code needs test-scope types (junit, assertj) resolvable. When they are
            // not, the whole model build throws -- and refusing every candidate because of
            // that would be worse than checking main alone. Retry narrower and record that
            // the answer is weaker, rather than silently downgrading it.
            testsModelled = false;
            launcher = newLauncher(root, classpath, compliance, false);
            try {
                launcher.buildModel();
            } catch (Throwable t2) {
                failure = t2;
            }
        }
        if (failure != null) {
            // Swallowing this reported every candidate as "type not found in any source
            // root", which is not what went wrong. With setNoClasspath(false) an incomplete
            // classpath makes the build throw, and that is a different problem with a
            // different fix.
            for (JsonNode e : new ArrayList<>(candidates)) {
                ObjectNode n = illegal.addObject();
                n.set("edit", e);
                n.put("why", "model build failed for " + root.getFileName() + ": "
                             + failure.getClass().getSimpleName() + ": "
                             + String.valueOf(failure.getMessage()));
                n.putArray("companions");
            }
            pending.removeAll(candidates);
            return;
        }

        // Types sharing a group move together, so each is judged with the others in hand.
        java.util.Map<String, java.util.Set<String>> groups = new java.util.HashMap<>();
        for (JsonNode e : candidates) {
            String g = e.path("group").asText("");
            if (!g.isEmpty())
                groups.computeIfAbsent(g, k -> new java.util.LinkedHashSet<>())
                      .add(e.path("type").asText());
        }

        List<JsonNode> done = new ArrayList<>();
        for (JsonNode edit : candidates) {
            String fqn = edit.path("type").asText();
            CtType<?> type = launcher.getFactory().Type().get(fqn);
            if (type == null || type.getPosition() == null
                    || !type.getPosition().isValidPosition()) continue;
            String to = edit.path("toPackage").asText();
            java.util.Set<String> moving =
                groups.getOrDefault(edit.path("group").asText(""), java.util.Collections.emptySet());
            String why;
            if ("invertEdge".equals(edit.path("op").asText("moveClass"))) {
                why = classpath.length > 0
                      ? groupPartition(launcher, edit.path("types"), to,
                                       new java.util.LinkedHashMap<>(), new ArrayList<>())
                      : "invertEdge needs a classpath";
            } else if ("extractInterface".equals(edit.path("op").asText("moveClass"))) {
                why = classpath.length > 0
                      ? (useConstraints ? constraintReason(type, to, new ArrayList<>())
                                        : extractIllegalReason(type, to, new ArrayList<>()))
                      : "extractInterface needs a classpath to resolve the consumer's calls";
            } else {
                why = classpath.length > 0 ? illegalReason(type, to, moving) : null;
            }
            ObjectNode n = (why == null ? legal : illegal).addObject();
            n.set("edit", edit);
            // A "legal" verdict reached without test sources in the model is weaker than one
            // reached with them; the caller is told which it got.
            n.put("testsModelled", testsModelled);
            if (why != null) {
                n.put("why", why);
                ArrayNode cs = n.putArray("companions");
                for (String c : companions(type)) cs.add(c);
            }
            done.add(edit);
        }
        pending.removeAll(done);
    }

    private static void applyInRoot(Path root, Path outDir, String[] classpath, int compliance,
                                    List<JsonNode> pending, ArrayNode applied,
                                    ArrayNode skipped, ArrayNode changed, ObjectMapper om) {
        if (!Files.isDirectory(root)) return;
        // Cheap pre-filter: no file named after the target type means no reason to spend a
        // full model build on this root.
        List<JsonNode> candidates = new ArrayList<>();
        for (JsonNode e : pending) if (hasFileFor(root, e.path("type").asText())) candidates.add(e);
        if (candidates.isEmpty()) return;

        Launcher launcher = new Launcher();
        launcher.addInputResource(root.toString());
        // A real classpath is what lets Spoon answer access questions itself. Run without
        // one and every reference has to be repaired afterwards by hand, which is how four
        // separate classes of access error each came to be found only by compiling.
        if (classpath.length > 0) {
            launcher.getEnvironment().setNoClasspath(false);
            launcher.getEnvironment().setSourceClasspath(classpath);
        } else {
            launcher.getEnvironment().setNoClasspath(true);
        }
        // Same tolerance the precheck uses, or the two paths disagree: precheck said all eight
        // log4j2 candidates were legal and every one then failed to APPLY on the identical
        // package-info.java. Two launcher configurations that can drift apart is the real
        // defect here; this keeps them in step until they share one builder.
        launcher.getEnvironment().setIgnoreSyntaxErrors(true);
        launcher.getEnvironment().setAutoImports(true);       // emit imports for moved types
        launcher.getEnvironment().setCommentEnabled(true);    // keep javadoc and comments
        launcher.getEnvironment().setComplianceLevel(compliance);
        // NOT the sniper printer. Sniper preserves original formatting by slicing the
        // original source text, and a type that has been detached from its compilation unit
        // - which reparenting requires - no longer has any. The default printer reformats
        // every file in this source root, which is acceptable here only because the target
        // is a throwaway copy measured by Arcan, never a patch a human reads.
        // ponytail: reformats the modeled root; needs sniper or a per-CU printer for patches
        // Print to a SCRATCH directory, never over the repo. The default printer rewrites
        // every compilation unit it modelled, and on log4j2 that damaged files the edit
        // never touched — a nested-type import came out as "package ThreadContext does not
        // exist" in a file nobody asked to move. The caller copies back only what moved.
        launcher.setSourceOutputDirectory(outDir.toFile());
        try {
            launcher.buildModel();
        } catch (Throwable t) {
            // Record it: a silent return here looks identical to "the type lives elsewhere".
            ObjectNode n = skipped.addObject();
            n.put("why", "model build failed for " + root.getFileName() + ": "
                         + t.getClass().getSimpleName() + ": "
                         + String.valueOf(t.getMessage()));
            return;
        }

        // The precheck judges a group together; judging it alone here refuses what it allowed.
        java.util.Map<String, java.util.Set<String>> groups = new java.util.HashMap<>();
        for (JsonNode e : candidates) {
            String g = e.path("group").asText("");
            if (!g.isEmpty())
                groups.computeIfAbsent(g, k -> new java.util.LinkedHashSet<>())
                      .add(e.path("type").asText());
        }

        Set<Path> removals = new LinkedHashSet<>();
        List<JsonNode> done = new ArrayList<>();
        for (JsonNode edit : candidates) {
            String fqn = edit.path("type").asText();
            CtType<?> type = launcher.getFactory().Type().get(fqn);
            if (type == null || type.getPosition() == null || !type.getPosition().isValidPosition()) continue;
            String from = type.getPackage() == null ? "" : type.getPackage().getQualifiedName();
            String to = edit.path("toPackage").asText();
            if (to.isEmpty() || to.equals(from)) continue;

            if ("invertEdge".equals(edit.path("op").asText("moveClass"))) {
                java.util.LinkedHashMap<CtType<?>, List<CtMethod<?>>> group =
                        new java.util.LinkedHashMap<>();
                List<String> refusedInGroup = new ArrayList<>();
                String bad = classpath.length > 0
                             ? groupPartition(launcher, edit.path("types"), to, group,
                                              refusedInGroup)
                             : "invertEdge needs a classpath";
                if (bad != null) {
                    ObjectNode sk = skipped.addObject();
                    sk.set("edit", edit);
                    sk.put("why", bad);
                } else {
                    applyInvertEdge(launcher, root, outDir, edit, to, group, refusedInGroup,
                                    applied);
                }
                done.add(edit);
                continue;
            }
            if ("extractInterface".equals(edit.path("op").asText("moveClass"))) {
                List<CtMethod<?>> methods = new ArrayList<>();
                String bad = classpath.length > 0
                             ? (useConstraints ? constraintReason(type, to, methods)
                                               : extractIllegalReason(type, to, methods))
                             : "extractInterface needs a classpath to resolve the consumer's calls";
                if (bad != null) {
                    ObjectNode sk = skipped.addObject();
                    sk.set("edit", edit);
                    sk.put("why", bad);
                } else {
                    applyExtractInterface(launcher, root, outDir, edit, type, to, methods, applied);
                }
                done.add(edit);
                continue;
            }

            java.util.Set<String> moving =
                groups.getOrDefault(edit.path("group").asText(""), java.util.Collections.emptySet());
            String why = classpath.length > 0 ? illegalReason(type, to, moving) : null;
            if (why != null) {
                ObjectNode sk = skipped.addObject();
                sk.set("edit", edit);
                sk.put("why", why);
                done.add(edit);          // decided; do not retry in another root
                continue;
            }

            File old = type.getPosition().getFile();
            String oldFqn = fqn;
            CtPackage target = launcher.getFactory().Package().getOrCreate(to);
            // Moving a top-level type is three edits, not one. Dropping it from the old
            // compilation unit's declared types is the one that is easy to miss: leave it
            // listed and the printer walks a type that is no longer there and NPEs.
            // Dropping the type from the old compilation unit's declared types is the step
            // that is easy to miss: leave it listed and the printer later walks a type that
            // is no longer there and dies on a null.
            CtCompilationUnit cu = type.getPosition().getCompilationUnit();
            if (cu != null) {
                List<CtType<?>> remaining = new ArrayList<>(cu.getDeclaredTypes());
                remaining.remove(type);
                cu.setDeclaredTypes(remaining);
            }
            type.delete();                 // detach: Spoon rejects re-parenting a live node
            target.addType(type);
            launcher.getFactory().CompilationUnit().getOrCreate(type);   // CU at the new path
            retarget(launcher, fqn, to);
            if (old != null) removals.add(old.toPath());
            ObjectNode a = applied.addObject();
            a.put("op", "moveClass");
            a.put("type", oldFqn);
            a.put("fromPackage", from);
            a.put("toPackage", to);
            a.put("root", root.toString());
            a.put("oldPath", old == null ? "" : old.toString());
            // Where the printer will put it, so the caller can copy back exactly this file.
            a.put("newPath", outDir.resolve(to.replace('.', File.separatorChar))
                                   .resolve(type.getSimpleName() + ".java").toString());
            done.add(edit);
        }
        if (done.isEmpty()) return;

        launcher.prettyprint();
        for (Path old : removals) {
            changed.add(old.toString());   // caller deletes; nothing here writes into the repo
        }
        pending.removeAll(done);
    }

    /**
     * Point every reference at the type's new package.
     *
     * Reparenting a CtType does NOT move the CtTypeReferences that name it -- each one holds
     * its own package reference. Skip this and the move looks perfect and does not compile:
     * callers in the old package silently keep resolving a type that is no longer there.
     */
    private static void retarget(Launcher launcher, String oldFqn, String newPkg) {
        String simple = oldFqn.substring(oldFqn.lastIndexOf('.') + 1);
        for (CtTypeReference<?> ref :
                launcher.getModel().getElements(new TypeFilter<>(CtTypeReference.class))) {
            if (simple.equals(ref.getSimpleName()) && oldFqn.equals(ref.getQualifiedName())) {
                ref.setPackage(launcher.getFactory().Package().createReference(newPkg));
            }
        }
    }

    private static boolean hasFileFor(Path root, String fqn) {
        if (fqn == null || fqn.isEmpty()) return false;
        String simple = fqn.substring(fqn.lastIndexOf('.') + 1) + ".java";
        try (Stream<Path> s = Files.walk(root)) {
            return s.anyMatch(p -> p.getFileName().toString().equals(simple));
        } catch (IOException e) {
            return false;
        }
    }

    /* ------------------------------------------------------------------ *
     *  extractInterface: Dependency Inversion, the technique that actually
     *  breaks a package cycle.
     *
     *  moveClass can only cut a cycle when ONE class is the entire bridge
     *  between two packages. Measured over 73 candidates across four
     *  repositories, 70 targeted a Cyclic Dependency and 59 of them changed
     *  nothing, because that condition almost never holds.
     *
     *  DIP inverts the edge instead of relocating it. Given consumer package
     *  P1 using P2.Service:
     *      - the abstraction is owned by the CONSUMER, so the interface is
     *        created in P1, not in P2 and not somewhere neutral;
     *      - P2.Service implements P1.ServiceApi, which is a P2 -> P1 edge,
     *        the direction that already existed;
     *      - P1's references are retargeted to its own interface, so the
     *        P1 -> P2 edge disappears.
     *  What is left points one way only.
     * ------------------------------------------------------------------ */

    /** The top-level type a declaration belongs to — nested types print into its file. */
    private static CtType<?> topLevel(CtType<?> t) {
        while (t != null && t.getDeclaringType() != null) t = t.getDeclaringType();
        return t;
    }

    private static boolean inPackage(CtType<?> t, String pkg) {
        return t != null && t.getPackage() != null
               && pkg.equals(t.getPackage().getQualifiedName());
    }

    /** Is this type nameable from `pkg` — i.e. public, or already living there? */
    private static boolean visibleFrom(CtTypeReference<?> ref, String pkg) {
        if (ref == null) return true;
        if (ref.isPrimitive()) return true;
        CtType<?> decl = ref.getTypeDeclaration();
        if (decl == null) return true;           // outside the model: a JDK or library type
        if (inPackage(decl, pkg)) return true;
        CtType<?> top = topLevel(decl);
        return top != null && top.getModifiers().contains(ModifierKind.PUBLIC);
    }

    /**
     * Constraint-based legality: which declarations can move, rather than whether any bad
     * usage exists anywhere.
     *
     * Set -Ddsarp.constraints=false to fall back to the old checklist. It is kept only so the
     * two can be compared on the same candidates; the checklist leaked four times and was
     * still leaking on generic containers when it was retired.
     */
    private static boolean useConstraints =
            !"false".equalsIgnoreCase(System.getProperty("dsarp.constraints", "true"));

    private static String constraintReason(CtType<?> type, String consumerPkg,
                                           List<CtMethod<?>> out) {
        // Structural refusals the constraint solver does not speak to: it decides which
        // DECLARATIONS may change, and these are facts about the type itself.
        if (!(type instanceof spoon.reflect.declaration.CtClass))
            return type.getSimpleName() + " is not a class";
        if (!type.getModifiers().contains(ModifierKind.PUBLIC))
            return type.getSimpleName() + " is not public";
        if (!type.getFormalCtTypeParameters().isEmpty())
            return type.getSimpleName() + " is generic; not supported yet";
        final String self = type.getQualifiedName();
        CtModel model = type.getFactory().getModel();
        for (CtType<?> sub : model.getElements(new TypeFilter<>(CtType.class))) {
            if (!inPackage(topLevel(sub), consumerPkg)) continue;
            CtTypeReference<?> sup = sub.getSuperclass();
            if (sup != null && self.equals(sup.getQualifiedName()))
                return sub.getSimpleName() + " extends " + type.getSimpleName()
                       + "; an extends clause cannot name an interface";
        }

        TypeConstraints.Result r = TypeConstraints.solve(model, type, consumerPkg);
        if (r.totalSlots == 0)
            return consumerPkg + " declares nothing of type " + type.getSimpleName();
        if (r.retargetable.isEmpty())
            return "no declaration of " + type.getSimpleName() + " can move: "
                   + first(r.blocked);
        if (r.methods.isEmpty())
            return consumerPkg + " calls no instance method on the movable declarations";
        for (CtMethod<?> m : r.methods) {
            if (!visibleFrom(m.getType(), consumerPkg))
                return m.getSimpleName() + "() returns a type not visible from " + consumerPkg;
            for (spoon.reflect.declaration.CtParameter<?> prm : m.getParameters())
                if (!visibleFrom(prm.getType(), consumerPkg))
                    return m.getSimpleName() + "() takes a type not visible from " + consumerPkg;
        }
        out.addAll(r.methods);
        return null;
    }

    private static String first(java.util.Map<String, String> m) {
        for (java.util.Map.Entry<String, String> e : m.entrySet())
            return e.getKey() + " " + e.getValue();
        return "no reason recorded";
    }

    /**
     * Why this type cannot have an interface extracted for `consumerPkg`, or null.
     * On success `out` holds the methods the consumer actually calls — the interface is
     * built from those alone, because an interface carrying everything the class happens to
     * expose is a second copy of the class, not an abstraction.
     */
    private static boolean conservative =
            !"false".equalsIgnoreCase(System.getProperty("dsarp.conservative", "false"));

    private static String extractIllegalReason(CtType<?> type, String consumerPkg,
                                               List<CtMethod<?>> out) {
        final String self = type.getQualifiedName();
        if (!(type instanceof spoon.reflect.declaration.CtClass))
            return type.getSimpleName() + " is not a class";
        if (!type.getModifiers().contains(ModifierKind.PUBLIC))
            return type.getSimpleName() + " is not public, so " + consumerPkg
                   + " cannot implement against it";
        if (!type.getFormalCtTypeParameters().isEmpty())
            return type.getSimpleName() + " is generic; extracting a generic interface is"
                   + " not supported yet";

        CtModel model = type.getFactory().getModel();

        // Constructed by the consumer -> the consumer needs the concrete class to exist.
        // Inverting that needs a factory as well, which is a bigger change than this op.
        for (spoon.reflect.code.CtConstructorCall<?> cc :
                model.getElements(new TypeFilter<>(spoon.reflect.code.CtConstructorCall.class))) {
            if (cc.getType() == null || !self.equals(cc.getType().getQualifiedName())) continue;
            CtType<?> user = cc.getParent(CtType.class);
            if (inPackage(topLevel(user), consumerPkg))
                return consumerPkg + " constructs " + type.getSimpleName()
                       + " directly; inverting that needs a factory too";
        }
        // Fields cannot move to an interface, and statics do not transfer to implementors.
        for (CtFieldReference<?> fr : model.getElements(new TypeFilter<>(CtFieldReference.class))) {
            if (fr.getDeclaringType() == null
                || !self.equals(fr.getDeclaringType().getQualifiedName())) continue;
            CtType<?> user = fr.getParent(CtType.class);
            if (inPackage(topLevel(user), consumerPkg))
                return consumerPkg + " reads field " + type.getSimpleName() + "."
                       + fr.getSimpleName() + ", which an interface cannot declare";
        }

        java.util.LinkedHashSet<CtMethod<?>> used = new java.util.LinkedHashSet<>();
        for (CtExecutableReference<?> er :
                model.getElements(new TypeFilter<>(CtExecutableReference.class))) {
            if (er.getDeclaringType() == null
                || !self.equals(er.getDeclaringType().getQualifiedName())) continue;
            CtType<?> user = er.getParent(CtType.class);
            if (!inPackage(topLevel(user), consumerPkg)) continue;
            Object decl = er.getExecutableDeclaration();
            if (!(decl instanceof CtMethod)) continue;          // constructors handled above
            CtMethod<?> m = (CtMethod<?>) decl;
            if (m.getModifiers().contains(ModifierKind.STATIC))
                return consumerPkg + " calls static " + type.getSimpleName() + "."
                       + m.getSimpleName() + "(); statics do not transfer to an interface";
            if (!m.getModifiers().contains(ModifierKind.PUBLIC))
                return consumerPkg + " calls non-public " + type.getSimpleName() + "."
                       + m.getSimpleName() + "()";
            used.add(m);
        }
        if (used.isEmpty())
            return consumerPkg + " calls no instance method of " + type.getSimpleName()
                   + "; nothing to abstract";

        // Subclassing is not a use that an interface can stand in for. pdfbox's
        // PDImageXObject EXTENDS PDXObject and lives in the consumer package, so retargeting
        // rewrote the inheritance itself: "PDImageXObject is not abstract and does not
        // override abstract method getCOSObject()", plus 92 cascading symbol errors. An
        // extends clause names a class and only a class.
        for (CtType<?> sub : model.getElements(new TypeFilter<>(CtType.class))) {
            if (!inPackage(topLevel(sub), consumerPkg)) continue;
            CtTypeReference<?> sup = sub.getSuperclass();
            if (sup != null && self.equals(sup.getQualifiedName()))
                return sub.getSimpleName() + " in " + consumerPkg + " extends "
                       + type.getSimpleName() + "; an extends clause cannot name an interface";
            for (CtTypeReference<?> si : sub.getSuperInterfaces())
                if (si != null && self.equals(si.getQualifiedName()))
                    return sub.getSimpleName() + " already implements " + type.getSimpleName();
        }

        // CONSERVATIVE MODE: refuse anything whose retargeted value could leave the file.
        //
        // The escape checks below are a checklist, and a checklist keeps leaking. Four rules
        // were added, each after a real build failure, and CFFFont still fails -- most likely
        // through a generic container, where the argument's own type is java.util.List and the
        // class never appears where the check is looking. Casts, wildcards and bounded type
        // parameters are further routes nobody has hit yet.
        //
        // Deciding this properly is the type-constraints problem. Until Eclipse JDT's
        // implementation is embedded, `conservative` buys soundness by giving up reach: only
        // abstract a type when every consumer declaration of it is a PRIVATE field or a local
        // variable, which cannot be seen outside the file that declares it, so no signature
        // elsewhere can demand the class. Fewer edges cut, nothing silently broken.
        if (conservative) {
            for (spoon.reflect.declaration.CtField<?> fld :
                    model.getElements(new TypeFilter<>(spoon.reflect.declaration.CtField.class))) {
                CtType<?> owner = topLevel(fld.getDeclaringType());
                if (!inPackage(owner, consumerPkg)) continue;
                if (fld.getType() == null || !self.equals(fld.getType().getQualifiedName()))
                    continue;
                if (!fld.getModifiers().contains(ModifierKind.PRIVATE))
                    return "conservative: " + owner.getSimpleName() + "." + fld.getSimpleName()
                           + " is a non-private " + type.getSimpleName() + " field, so the"
                           + " value can escape the file";
            }
            for (spoon.reflect.declaration.CtParameter<?> prm :
                    model.getElements(new TypeFilter<>(spoon.reflect.declaration.CtParameter.class))) {
                CtType<?> owner = topLevel(prm.getParent(CtType.class));
                if (!inPackage(owner, consumerPkg)) continue;
                if (prm.getType() == null || !self.equals(prm.getType().getQualifiedName()))
                    continue;
                spoon.reflect.declaration.CtExecutable<?> exe =
                        prm.getParent(spoon.reflect.declaration.CtExecutable.class);
                boolean priv = exe instanceof spoon.reflect.declaration.CtModifiable
                        && ((spoon.reflect.declaration.CtModifiable) exe).getModifiers()
                               .contains(ModifierKind.PRIVATE);
                if (!priv)
                    return "conservative: " + owner.getSimpleName() + " takes "
                           + type.getSimpleName() + " in a non-private signature";
            }
            for (CtMethod<?> m : model.getElements(new TypeFilter<>(CtMethod.class))) {
                CtType<?> owner = topLevel(m.getDeclaringType());
                if (!inPackage(owner, consumerPkg)) continue;
                if (m.getType() == null || !self.equals(m.getType().getQualifiedName())) continue;
                if (!m.getModifiers().contains(ModifierKind.PRIVATE))
                    return "conservative: " + owner.getSimpleName() + "." + m.getSimpleName()
                           + "() returns " + type.getSimpleName() + " from a non-private"
                           + " signature";
            }
        }

        // Where do the consumer's values of this type ESCAPE to?
        //
        // Retargeting a declaration changes the type of every expression that reads it, so a
        // field the consumer now holds as the interface cannot be handed to a signature that
        // still demands the class. pdfbox failed exactly here: PDFDebugger was abstracted for
        // streampane, and streampane passes it onward to a constructor declared elsewhere —
        // "incompatible types: PDFDebuggerApi cannot be converted to PDFDebugger". Checking
        // the calls the consumer makes ON the type is not enough; this checks where values of
        // it are allowed to go.
        for (spoon.reflect.code.CtAbstractInvocation<?> inv :
                model.getElements(new TypeFilter<>(spoon.reflect.code.CtAbstractInvocation.class))) {
            if (!(inv instanceof spoon.reflect.declaration.CtElement)) continue;
            CtType<?> site = topLevel(((spoon.reflect.declaration.CtElement) inv)
                                          .getParent(CtType.class));
            if (!inPackage(site, consumerPkg)) continue;          // not the consumer's problem
            CtExecutableReference<?> exe = inv.getExecutable();
            if (exe == null || exe.getDeclaringType() == null) continue;
            CtType<?> callee = exe.getDeclaringType().getTypeDeclaration();
            if (inPackage(topLevel(callee), consumerPkg)) continue;  // stays inside, retargeted too
            for (Object argO : inv.getArguments()) {
                if (!(argO instanceof spoon.reflect.code.CtExpression)) continue;
                CtTypeReference<?> at = ((spoon.reflect.code.CtExpression<?>) argO).getType();
                if (at != null && self.equals(at.getQualifiedName()))
                    return consumerPkg + " passes a " + type.getSimpleName() + " to "
                           + exe.getSimpleName() + "() outside the package, which still"
                           + " expects the class, not an interface";
            }
        }

        // The same escape, through an assignment rather than an argument. A retargeted value
        // written into a slot that is still typed as the class narrows the interface back to
        // the implementation, which does not compile: pdfbox produced eight of
        // "CFFFontApi cannot be converted to CFFFont" this way.
        //
        // This is a filter, not a proof. Deciding every position a retargeted declaration can
        // reach is the type-constraints problem (Tip, Kiezun, Baeumer), and the compile gate
        // is what actually keeps the pipeline honest -- a candidate that slips through here is
        // recorded as compiled=false and scored zero, never as a success.
        for (spoon.reflect.code.CtAssignment<?, ?> asg :
                model.getElements(new TypeFilter<>(spoon.reflect.code.CtAssignment.class))) {
            CtType<?> site = topLevel(asg.getParent(CtType.class));
            if (!inPackage(site, consumerPkg)) continue;
            spoon.reflect.code.CtExpression<?> lhs = asg.getAssigned();
            spoon.reflect.code.CtExpression<?> rhs = asg.getAssignment();
            if (lhs == null || rhs == null || lhs.getType() == null || rhs.getType() == null)
                continue;
            if (!self.equals(rhs.getType().getQualifiedName())) continue;
            if (lhs instanceof spoon.reflect.code.CtFieldAccess) {
                CtFieldReference<?> fr = ((spoon.reflect.code.CtFieldAccess<?>) lhs).getVariable();
                if (fr != null && fr.getDeclaringType() != null) {
                    CtType<?> owner = fr.getDeclaringType().getTypeDeclaration();
                    if (owner != null && !inPackage(topLevel(owner), consumerPkg))
                        return consumerPkg + " assigns a " + type.getSimpleName()
                               + " into " + owner.getSimpleName() + "." + fr.getSimpleName()
                               + ", declared outside the package as the class";
                }
            }
        }
        // A consumer method that OVERRIDES one declared elsewhere cannot widen its return
        // type to the interface: the supertype still promises the class.
        for (CtMethod<?> m : model.getElements(new TypeFilter<>(CtMethod.class))) {
            CtType<?> owner = topLevel(m.getDeclaringType());
            if (!inPackage(owner, consumerPkg)) continue;
            if (m.getType() == null || !self.equals(m.getType().getQualifiedName())) continue;
            for (CtMethod<?> sup : m.getTopDefinitions()) {
                CtType<?> supOwner = topLevel(sup.getDeclaringType());
                if (supOwner != null && !inPackage(supOwner, consumerPkg))
                    return m.getSimpleName() + "() overrides a method declared outside "
                           + consumerPkg + " that returns " + type.getSimpleName();
            }
        }

        // Every type named in a kept signature has to be nameable from the consumer package,
        // or the interface itself will not compile there.
        for (CtMethod<?> m : used) {
            if (!visibleFrom(m.getType(), consumerPkg))
                return m.getSimpleName() + "() returns " + m.getType().getSimpleName()
                       + ", which is not visible from " + consumerPkg;
            for (spoon.reflect.declaration.CtParameter<?> p : m.getParameters())
                if (!visibleFrom(p.getType(), consumerPkg))
                    return m.getSimpleName() + "() takes " + p.getType().getSimpleName()
                           + ", which is not visible from " + consumerPkg;
            for (CtTypeReference<? extends Throwable> th : m.getThrownTypes())
                if (!visibleFrom(th, consumerPkg))
                    return m.getSimpleName() + "() throws " + th.getSimpleName()
                           + ", which is not visible from " + consumerPkg;
        }
        out.addAll(used);
        return null;
    }

    /**
     * The transformation itself, for ONE implementation class. Returns the consumer types
     * whose references were retargeted, so the caller knows which files to patch.
     *
     * Split out from the edit handling because inverting a package edge means doing this for
     * every class the consumer names on the far side: cutting one reference out of twenty-five
     * leaves the package edge exactly where it was, and Arcan counts the edge.
     */
    private static java.util.LinkedHashSet<CtType<?>> doExtract(
            Launcher launcher, CtType<?> type, String consumerPkg, String ifaceName,
            List<CtMethod<?>> methods) {
        CtPackage pkg = launcher.getFactory().Package().getOrCreate(consumerPkg);
        spoon.reflect.declaration.CtInterface<?> iface =
                launcher.getFactory().Interface().create(pkg, ifaceName);
        iface.addModifier(ModifierKind.PUBLIC);

        for (CtMethod<?> m : methods) {
            CtMethod<?> copy = m.clone();
            copy.setBody(null);
            // @Override on an interface method with no supertype does not compile, and the
            // implementation's annotations say nothing about the contract.
            copy.setAnnotations(new ArrayList<>());
            copy.setModifiers(java.util.EnumSet.of(ModifierKind.PUBLIC, ModifierKind.ABSTRACT));
            iface.addMethod(copy);
        }
        launcher.getFactory().CompilationUnit().getOrCreate(iface);
        type.addSuperInterface((CtTypeReference) iface.getReference());

        // Retarget DECLARATIONS ONLY, and only the ones the constraint solver cleared.
        //
        // Rewriting every reference to the class is what an earlier version did, and it does
        // not survive contact with `new Meter()`: the constructor call is a reference too, so
        // the field became `MeterApi meter = new MeterApi()` and javac said "MeterApi is
        // abstract; cannot be instantiated". A declaration's type changing says nothing about
        // what is assigned into it -- that asymmetry is the whole reason constraints beat a
        // reference sweep.
        java.util.LinkedHashSet<CtType<?>> touched = new java.util.LinkedHashSet<>();
        CtTypeReference<?> ifaceRef = iface.getReference();
        TypeConstraints.Result solved =
                TypeConstraints.solve(launcher.getModel(), type, consumerPkg);
        for (spoon.reflect.declaration.CtElement d : solved.retargetable) {
            if (d instanceof spoon.reflect.declaration.CtVariable) {
                ((spoon.reflect.declaration.CtVariable) d).setType(ifaceRef.clone());
            } else if (d instanceof CtMethod) {
                ((CtMethod) d).setType(ifaceRef.clone());
            } else {
                continue;
            }
            CtType<?> user = topLevel(d.getParent(CtType.class));
            if (user != null && user != iface) touched.add(user);
        }
        return touched;
    }

    /** Apply one extractInterface edit. */
    private static void applyExtractInterface(Launcher launcher, Path root, Path outDir,
                                              JsonNode edit, CtType<?> type, String consumerPkg,
                                              List<CtMethod<?>> methods, ArrayNode applied) {
        String ifaceName = edit.path("interfaceName").asText(type.getSimpleName() + "Api");
        String self = type.getQualifiedName();
        java.util.LinkedHashSet<CtType<?>> touched =
                doExtract(launcher, type, consumerPkg, ifaceName, methods);

        ObjectNode a = applied.addObject();
        a.put("op", "extractInterface");
        a.put("type", self);
        a.put("toPackage", consumerPkg);
        a.put("interfaceFqn", consumerPkg + "." + ifaceName);
        a.put("methods", methods.size());
        a.put("consumersRetargeted", touched.size());
        a.put("root", root.toString());
        // Explicit scratch -> repo pairs. Unlike a move there is nothing to delete: one file
        // is created and the rest are edited in place.
        // Only the INTERFACE is taken from the printer; it is new, so there is no original
        // formatting to lose. The implementation and the consumers are patched textually by
        // the caller, because the default printer reformats every file it models and pdfbox
        // rejected two candidates on `Line is longer than 200 characters` with no javac error
        // at all -- the transformation was fine and the reflow failed the style gate.
        ArrayNode writes = a.putArray("writes");
        addWrite(writes, outDir, root, consumerPkg, ifaceName, "interface");
        CtType<?> implTop = topLevel(type);
        addWrite(writes, outDir, root, implTop.getPackage().getQualifiedName(),
                 implTop.getSimpleName(), "impl");
        for (CtType<?> t : touched)
            addWrite(writes, outDir, root, t.getPackage().getQualifiedName(),
                     t.getSimpleName(), "consumer");
    }

    /**
     * Split the group into what CAN be inverted and what cannot. Returns null when anything
     * is invertible, and a reason only when nothing is.
     *
     * This was all-or-nothing, on the argument that a group which cannot be completed cannot
     * close the package edge. Measurement refused that argument: FontHeaders named two classes
     * across the boundary, only part of its edge was inverted, and the smell count still fell
     * (targeted -1, collateral -1, tests clean). Meanwhile all-or-nothing rejected 43 of 45
     * pdfbox candidates and both survivors turned out to contain a single class, so the group
     * operation never actually ran as a group on real code.
     *
     * Partial inversion it is. The per-class rules are untouched — every one of them was
     * added because a real build failed — and the compile gate still decides the outcome.
     */
    private static String groupPartition(Launcher launcher, JsonNode types, String consumerPkg,
                                         java.util.LinkedHashMap<CtType<?>, List<CtMethod<?>>> out,
                                         List<String> refused) {
        if (types == null || types.size() == 0) return "no implementation types given";
        for (JsonNode n : types) {
            String fqn = n.asText();
            CtType<?> t = launcher.getFactory().Type().get(fqn);
            if (t == null || t.getPosition() == null || !t.getPosition().isValidPosition()) {
                refused.add(fqn + ": not in this source root");
                continue;
            }
            List<CtMethod<?>> ms = new ArrayList<>();
            String why = useConstraints ? constraintReason(t, consumerPkg, ms)
                                        : extractIllegalReason(t, consumerPkg, ms);
            if (why != null) {
                refused.add(t.getSimpleName() + ": " + why);
                continue;
            }
            out.put(t, ms);
        }
        if (out.isEmpty())
            return refused.isEmpty() ? "no invertible type in the group"
                                     : refused.get(0);
        return null;
    }

    /** Invert every reference from `consumerPkg` into one implementation package at once. */
    private static void applyInvertEdge(Launcher launcher, Path root, Path outDir,
                                        JsonNode edit, String consumerPkg,
                                        java.util.LinkedHashMap<CtType<?>, List<CtMethod<?>>> group,
                                        List<String> refusedInGroup, ArrayNode applied) {
        java.util.LinkedHashSet<CtType<?>> touched = new java.util.LinkedHashSet<>();
        List<String> created = new ArrayList<>();
        List<CtType<?>> impls = new ArrayList<>(group.keySet());
        int methodCount = 0;
        for (CtType<?> t : impls) {
            String ifaceName = t.getSimpleName() + "Api";
            List<CtMethod<?>> ms = group.get(t);
            methodCount += ms.size();
            touched.addAll(doExtract(launcher, t, consumerPkg, ifaceName, ms));
            created.add(consumerPkg + "." + ifaceName);
        }

        ObjectNode a = applied.addObject();
        a.put("op", "invertEdge");
        a.put("toPackage", consumerPkg);
        a.put("implPackage", impls.isEmpty() || impls.get(0).getPackage() == null ? ""
                             : impls.get(0).getPackage().getQualifiedName());
        a.put("classesInverted", impls.size());
        a.put("classesSkipped", refusedInGroup.size());
        ArrayNode why = a.putArray("skippedInGroup");
        for (String s : refusedInGroup) why.add(s);
        a.put("methods", methodCount);
        a.put("consumersRetargeted", touched.size());
        a.put("root", root.toString());
        ArrayNode ifaceArr = a.putArray("interfaces");
        for (String s : created) ifaceArr.add(s);
        ArrayNode pairs = a.putArray("pairs");
        for (CtType<?> t : impls) {
            ObjectNode pr = pairs.addObject();
            pr.put("type", t.getQualifiedName());
            pr.put("interfaceFqn", consumerPkg + "." + t.getSimpleName() + "Api");
        }
        ArrayNode writes = a.putArray("writes");
        for (CtType<?> t : impls) {
            addWrite(writes, outDir, root, consumerPkg, t.getSimpleName() + "Api", "interface");
            CtType<?> top = topLevel(t);
            addWrite(writes, outDir, root, top.getPackage().getQualifiedName(),
                     top.getSimpleName(), "impl")
                    .put("interfaceFqn", consumerPkg + "." + t.getSimpleName() + "Api");
        }
        for (CtType<?> t : touched)
            addWrite(writes, outDir, root, t.getPackage().getQualifiedName(),
                     t.getSimpleName(), "consumer");
    }

    private static ObjectNode addWrite(ArrayNode writes, Path outDir, Path root,
                                       String pkg, String simpleName, String kind) {
        String rel = pkg.replace('.', File.separatorChar) + File.separator + simpleName + ".java";
        ObjectNode w = writes.addObject();
        w.put("kind", kind);
        w.put("simpleName", simpleName);
        w.put("from", outDir.resolve(rel).toString());
        w.put("to", root.resolve(rel).toString());
        return w;
    }

    private ApplyEdits() {}
}
