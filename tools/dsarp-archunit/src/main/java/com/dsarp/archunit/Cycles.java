package com.dsarp.archunit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import com.tngtech.archunit.core.domain.Dependency;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Package dependency cycles, read from compiled classes.
 *
 * <pre>java -jar dsarp-archunit.jar &lt;out.json&gt; &lt;classesDir&gt; [classesDir...]</pre>
 *
 * Why this exists. Every ranking attempt in this project was scored against Arcan's
 * smell-count delta, and three in a row failed to generalise across repositories. One class
 * move accounts for -240 of the 325 smells ever removed here, so that target is dominated by
 * a single outlier and any model trained on it is largely predicting that one move.
 *
 * A cycle is a better unit of truth: it is either present or it is not. Asking "is THIS cycle
 * gone" gives a binary label per candidate that no outlier can distort.
 *
 * Bytecode, not source. Our own dependency graph matches text, so it cannot distinguish a
 * type named in a comment from one actually used, and it cannot see a dependency the compiler
 * introduced. ArchUnit's importer reads what the JVM will load.
 *
 * Cycle detection is Tarjan's, computed here rather than taken from ArchUnit's rule API,
 * because the rule reports violations as human-readable prose and parsing that would be
 * fragile in a way the importer is not.
 */
public final class Cycles {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: Cycles <out.json> <classesDir> [classesDir...]");
            System.exit(2);
        }
        Path out = Paths.get(args[0]);
        List<Path> roots = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            Path p = Paths.get(args[i]);
            if (p.toFile().isDirectory()) roots.add(p);
        }
        ObjectMapper om = new ObjectMapper();
        ObjectNode result = om.createObjectNode();
        if (roots.isEmpty()) {
            result.put("ok", false);
            result.put("why", "no existing class directory given");
            om.writerWithDefaultPrettyPrinter().writeValue(out.toFile(), result);
            System.out.println("cycles=0 (no class dirs)");
            return;
        }

        // Count what is on disk BEFORE importing. ArchUnit silently skips class files whose
        // version its bundled ASM cannot parse, and a silent zero here is catastrophic: no
        // classes means no cycles, which makes "the cycle is gone" vacuously true for every
        // candidate. Compiled on this JDK 26 box, javac emits major version 70 and ArchUnit
        // 1.3.0 read exactly none of it while reporting success.
        long onDisk = 0;
        for (Path r : roots) {
            try (java.util.stream.Stream<Path> s = java.nio.file.Files.walk(r)) {
                onDisk += s.filter(p -> p.toString().endsWith(".class")).count();
            }
        }
        JavaClasses classes = new ClassFileImporter().importPaths(roots);
        if (onDisk > 0 && classes.size() == 0) {
            result.put("ok", false);
            result.put("why", "found " + onDisk + " .class files but imported 0 — the class"
                              + " file version is probably newer than this ArchUnit's ASM");
            result.put("classFilesOnDisk", onDisk);
            om.writerWithDefaultPrettyPrinter().writeValue(out.toFile(), result);
            System.out.println("FAILED: " + onDisk + " class files, 0 importable");
            System.exit(3);
        }

        // Package -> packages it depends on. Self-edges are dropped: a package depending on
        // itself is not a cycle between packages, and keeping them would make every package a
        // trivial component.
        Map<String, Set<String>> edges = new HashMap<>();
        // How many class-level dependencies create each package edge. An edge
        // carried by one class can be inverted; one carried by forty cannot.
        Map<String, Integer> weight = new HashMap<>();
        Set<String> pkgs = new TreeSet<>();
        for (JavaClass c : classes) {
            String from = c.getPackageName();
            if (from == null || from.isEmpty()) continue;
            pkgs.add(from);
            for (Dependency d : c.getDirectDependenciesFromSelf()) {
                String to = d.getTargetClass().getPackageName();
                if (to == null || to.isEmpty() || to.equals(from)) continue;
                // Only dependencies INTO the analysed code; a cycle through the JDK is not a
                // cycle we can refactor, and importPaths never loaded those classes anyway.
                if (!classes.contain(d.getTargetClass().getName())) continue;
                edges.computeIfAbsent(from, k -> new LinkedHashSet<>()).add(to);
                weight.merge(from + " -> " + to, 1, Integer::sum);
                pkgs.add(to);
            }
        }

        List<Set<String>> components = tarjan(pkgs, edges);
        ArrayNode arr = result.putArray("cycles");
        ArrayNode cycleEdges = result.putArray("cycleEdges");
        int biggest = 0;
        for (Set<String> comp : components) {
            if (comp.size() < 2) continue;          // a single package is not a cycle
            biggest = Math.max(biggest, comp.size());
            ArrayNode c = arr.addArray();
            for (String p : new TreeSet<>(comp)) c.add(p);
            // The internal edges of this component, with weights, so the caller can ask what
            // it would actually take to break it rather than only that it exists.
            ArrayNode ea = cycleEdges.addArray();
            for (String from : new TreeSet<>(comp))
                for (String to : edges.getOrDefault(from, Set.of()))
                    if (comp.contains(to)) {
                        ObjectNode en = ea.addObject();
                        en.put("from", from);
                        en.put("to", to);
                        en.put("classes", weight.getOrDefault(from + " -> " + to, 1));
                    }
        }
        result.put("ok", true);
        result.put("classFilesOnDisk", onDisk);
        result.put("packages", pkgs.size());
        result.put("classes", classes.size());
        result.put("cycleCount", arr.size());
        result.put("largestCycle", biggest);
        om.writerWithDefaultPrettyPrinter().writeValue(out.toFile(), result);
        System.out.println("cycles=" + arr.size() + " packages=" + pkgs.size()
                           + " classes=" + classes.size());
    }

    /** Strongly connected components, iteratively — a deep package graph would blow a stack. */
    static List<Set<String>> tarjan(Set<String> nodes, Map<String, Set<String>> edges) {
        Map<String, Integer> index = new HashMap<>();
        Map<String, Integer> low = new HashMap<>();
        Set<String> onStack = new HashSet<>();
        Deque<String> stack = new ArrayDeque<>();
        List<Set<String>> out = new ArrayList<>();
        int[] counter = {0};

        for (String root : nodes) {
            if (index.containsKey(root)) continue;
            Deque<String> work = new ArrayDeque<>();
            Deque<java.util.Iterator<String>> iters = new ArrayDeque<>();
            work.push(root);
            index.put(root, counter[0]);
            low.put(root, counter[0]);
            counter[0]++;
            stack.push(root);
            onStack.add(root);
            iters.push(edges.getOrDefault(root, Set.of()).iterator());

            while (!work.isEmpty()) {
                String v = work.peek();
                java.util.Iterator<String> it = iters.peek();
                if (it.hasNext()) {
                    String w = it.next();
                    if (!nodes.contains(w)) continue;
                    if (!index.containsKey(w)) {
                        index.put(w, counter[0]);
                        low.put(w, counter[0]);
                        counter[0]++;
                        stack.push(w);
                        onStack.add(w);
                        work.push(w);
                        iters.push(edges.getOrDefault(w, Set.of()).iterator());
                    } else if (onStack.contains(w)) {
                        low.put(v, Math.min(low.get(v), index.get(w)));
                    }
                } else {
                    work.pop();
                    iters.pop();
                    if (!work.isEmpty()) {
                        String parent = work.peek();
                        low.put(parent, Math.min(low.get(parent), low.get(v)));
                    }
                    if (low.get(v).equals(index.get(v))) {
                        Set<String> comp = new LinkedHashSet<>();
                        String w;
                        do {
                            w = stack.pop();
                            onStack.remove(w);
                            comp.add(w);
                        } while (!w.equals(v));
                        out.add(comp);
                    }
                }
            }
        }
        return out;
    }

    private Cycles() {}
}
