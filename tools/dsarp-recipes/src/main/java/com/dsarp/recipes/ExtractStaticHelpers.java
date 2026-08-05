package com.dsarp.recipes;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.openrewrite.ExecutionContext;
import org.openrewrite.Option;
import org.openrewrite.Recipe;
import org.openrewrite.ScanningRecipe;
import org.openrewrite.SourceFile;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.JavaParser;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.Statement;
import org.openrewrite.java.tree.TypeUtils;

import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Extract a class's public static methods into a new helper type — done on the LST.
 *
 * <p>DSARP first attempted this as Python source surgery and it never produced compiling
 * Java. Three separate defects came out of that: the extracted file lost the original's
 * imports; cutting the declarations stranded every caller; and qualifying calls by regex
 * rewrote method DECLARATIONS into syntax errors. Each was a symptom of the same root cause —
 * text editing cannot see where a method really ends, which names are types, or which
 * identifiers are calls.
 *
 * <p>Here the whole transformation happens inside OpenRewrite, so the tree is valid at every
 * step and the recipe that repoints call sites can actually run afterwards:
 * <ol>
 *   <li>scan — collect the target class's public static methods and its imports;</li>
 *   <li>generate — emit the new helper source from those method declarations;</li>
 *   <li>visit — remove the same declarations from the original class.</li>
 * </ol>
 *
 * <p>Static methods cannot reference instance state, so moving them preserves behaviour. Pair
 * this with {@code ChangeMethodTargetToStatic} to repoint the call sites.
 */
public class ExtractStaticHelpers extends ScanningRecipe<ExtractStaticHelpers.Accumulator> {

    @Option(displayName = "Class",
            description = "Fully qualified name of the class to extract static methods from.",
            example = "com.example.GenericValidator")
    private final String fullyQualifiedClassName;

    @Option(displayName = "Target",
            description = "Fully qualified name of the helper class to create.",
            example = "com.example.GenericValidatorHelpers")
    private final String fullyQualifiedTargetTypeName;

    @Option(displayName = "Methods",
            description = "Comma-separated names of the methods to move. Only these are "
                    + "extracted; DSARP has already checked each one against preconditions "
                    + "the recipe cannot see, such as whether it calls a non-public member.",
            example = "isBlankOrNull,matchRegexp")
    private final String methodNames;

    @JsonCreator
    public ExtractStaticHelpers(
            @JsonProperty("fullyQualifiedClassName") String fullyQualifiedClassName,
            @JsonProperty("fullyQualifiedTargetTypeName") String fullyQualifiedTargetTypeName,
            @JsonProperty("methodNames") String methodNames) {
        this.fullyQualifiedClassName = fullyQualifiedClassName;
        this.fullyQualifiedTargetTypeName = fullyQualifiedTargetTypeName;
        this.methodNames = methodNames;
    }

    public String getMethodNames() {
        return methodNames;
    }

    private Set<String> wanted() {
        Set<String> out = new LinkedHashSet<>();
        if (methodNames != null) {
            for (String n : methodNames.split(",")) {
                if (!n.isEmpty()) {
                    out.add(n);
                }
            }
        }
        return out;
    }

    public String getFullyQualifiedClassName() {
        return fullyQualifiedClassName;
    }

    public String getFullyQualifiedTargetTypeName() {
        return fullyQualifiedTargetTypeName;
    }

    @Override
    public String getDisplayName() {
        return "Extract public static methods into a helper class";
    }

    @Override
    public String getDescription() {
        return "Moves a class's public static methods into a new final helper type, shrinking "
                + "the original. Static methods cannot touch instance state, so the move is "
                + "behaviour-preserving. Addresses Insufficient Modularization and "
                + "Multifaceted Abstraction, which relocation-based refactorings cannot fix.";
    }

    public static class Accumulator {
        // The printed SOURCE of each method, captured during the scan where a real
        // cursor exists. Printing in generate() with a fabricated Cursor(null, m)
        // fails with "Expected to find enclosing SourceFile".
        final List<String> methodSources = new ArrayList<>();
        final List<String> methodNames = new ArrayList<>();
        final Set<String> imports = new LinkedHashSet<>();
        String sourceDir = "";
        boolean generated;
    }

    @Override
    public Accumulator getInitialValue(ExecutionContext ctx) {
        return new Accumulator();
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getScanner(Accumulator acc) {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.CompilationUnit visitCompilationUnit(J.CompilationUnit cu,
                                                          ExecutionContext ctx) {
                boolean mine = cu.getClasses().stream().anyMatch(
                        c -> c.getType() != null
                                && TypeUtils.isOfClassType(c.getType(), fullyQualifiedClassName));
                if (!mine) {
                    return cu;
                }
                // Remember the original's imports: the moved bodies reference those types, and
                // omitting them was the first failure of the text-based attempt.
                cu.getImports().forEach(i -> acc.imports.add(i.printTrimmed(getCursor())));
                if (cu.getSourcePath().getParent() != null) {
                    acc.sourceDir = cu.getSourcePath().getParent().toString().replace('\\', '/');
                }
                return super.visitCompilationUnit(cu, ctx);
            }

            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration m,
                                                              ExecutionContext ctx) {
                // Only methods declared BY THE TARGET CLASS. Without this guard the scanner
                // collected every public static method in the repository, so the generated
                // helper referenced types the target never imported ("cannot find symbol:
                // class DateValidator").
                J.ClassDeclaration owner = getCursor().firstEnclosing(J.ClassDeclaration.class);
                boolean mine = owner != null && owner.getType() != null
                        && TypeUtils.isOfClassType(owner.getType(), fullyQualifiedClassName);
                if (mine && isExtractable(m)) {
                    acc.methodSources.add(m.printTrimmed(getCursor()));
                    acc.methodNames.add(m.getSimpleName());
                }
                return m;
            }
        };
    }

    @Override
    public Collection<SourceFile> generate(Accumulator acc, ExecutionContext ctx) {
        if (acc.methodSources.isEmpty() || acc.generated) {
            return Collections.emptyList();
        }
        acc.generated = true;

        String pkg = fullyQualifiedTargetTypeName.substring(
                0, fullyQualifiedTargetTypeName.lastIndexOf('.'));
        String simple = fullyQualifiedTargetTypeName.substring(
                fullyQualifiedTargetTypeName.lastIndexOf('.') + 1);

        StringBuilder src = new StringBuilder();
        src.append("package ").append(pkg).append(";\n\n");
        acc.imports.forEach(i -> src.append(i).append(";\n"));
        if (!acc.imports.isEmpty()) {
            src.append('\n');
        }
        src.append("/**\n * Static helpers extracted by DSARP to reduce the size of ")
           .append(fullyQualifiedClassName.substring(
                   fullyQualifiedClassName.lastIndexOf('.') + 1))
           .append(".\n * Static methods cannot reach instance state, so this preserves"
                   + " behaviour.\n */\n")
           .append("public final class ").append(simple).append(" {\n\n")
           .append("    private ").append(simple).append("() {\n    }\n\n");
        // These were printed from the LST during the scan, where a real cursor exists, so
        // each declaration is reproduced exactly — signature, generics, annotations, body.
        for (String body : acc.methodSources) {
            src.append("    ").append(body).append("\n\n");
        }
        src.append("}\n");

        String path = (acc.sourceDir.isEmpty() ? "" : acc.sourceDir + "/") + simple + ".java";
        return JavaParser.fromJavaVersion().build()
                .parse(ctx, src.toString())
                .map(s -> (SourceFile) s.withSourcePath(Paths.get(path)))
                .collect(Collectors.toList());
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor(Accumulator acc) {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration cd,
                                                            ExecutionContext ctx) {
                if (cd.getType() == null
                        || !TypeUtils.isOfClassType(cd.getType(), fullyQualifiedClassName)) {
                    return cd;
                }
                // Drop exactly the declarations that were collected. Working on the LST means
                // a method's true extent is known, rather than guessed at with brace counting.
                List<Statement> kept = cd.getBody().getStatements().stream()
                        .filter(st -> !(st instanceof J.MethodDeclaration)
                                || !isExtractable((J.MethodDeclaration) st))
                        .collect(Collectors.toList());
                if (kept.size() == cd.getBody().getStatements().size()) {
                    return cd;
                }
                return cd.withBody(cd.getBody().withStatements(kept));
            }
        };
    }

    private boolean isExtractable(J.MethodDeclaration m) {
        boolean isPublic = m.hasModifier(J.Modifier.Type.Public);
        boolean isStatic = m.hasModifier(J.Modifier.Type.Static);
        if (!isPublic || !isStatic || m.getBody() == null || m.isConstructor()) {
            return false;
        }
        // Honour DSARP's approved list. Extracting every public static method ignored the
        // preconditions checked upstream — including "does not call a non-public member" —
        // so methods that could not compile from their new home were moved anyway.
        Set<String> only = wanted();
        return only.isEmpty() || only.contains(m.getSimpleName());
    }
}
