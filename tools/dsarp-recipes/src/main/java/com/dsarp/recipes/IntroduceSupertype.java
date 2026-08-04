package com.dsarp.recipes;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.openrewrite.ExecutionContext;
import org.openrewrite.Option;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.ImplementInterface;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeUtils;

import java.util.Arrays;
import java.util.List;

/**
 * Make a set of unrelated classes share an explicit supertype.
 *
 * <p>This is the fix for two hierarchy smells that relocation cannot touch:
 * <ul>
 *   <li><b>Missing Hierarchy</b> — classes that clearly play the same role but have no common
 *       abstraction, so callers must special-case each one.</li>
 *   <li><b>Wide Hierarchy</b> — a supertype with too many direct children; grouping a cohesive
 *       subset under an intermediate abstraction narrows it.</li>
 * </ul>
 *
 * <p>rewrite-java ships {@code ImplementInterface} only as a visitor, so it cannot be named
 * from a declarative {@code rewrite.yml}. This recipe wraps it and pairs it with the interface
 * declaration itself, which DSARP writes to disk before the run (an empty interface is always
 * legal to implement, so the result compiles).
 */
public class IntroduceSupertype extends Recipe {

    @Option(displayName = "Interface",
            description = "Fully qualified name of the supertype the classes should implement.",
            example = "com.example.Validator")
    private final String fullyQualifiedInterfaceName;

    @Option(displayName = "Classes",
            description = "Comma-separated fully qualified names of the classes to change.",
            example = "com.example.AValidator,com.example.BValidator")
    private final String classNames;

    @JsonCreator
    public IntroduceSupertype(
            @JsonProperty("fullyQualifiedInterfaceName") String fullyQualifiedInterfaceName,
            @JsonProperty("classNames") String classNames) {
        this.fullyQualifiedInterfaceName = fullyQualifiedInterfaceName;
        this.classNames = classNames;
    }

    public String getFullyQualifiedInterfaceName() {
        return fullyQualifiedInterfaceName;
    }

    public String getClassNames() {
        return classNames;
    }

    @Override
    public String getDisplayName() {
        return "Introduce a shared supertype";
    }

    @Override
    public String getDescription() {
        return "Makes the listed classes implement a common interface, giving them the explicit "
                + "shared abstraction they lack. Addresses the Missing Hierarchy and Wide "
                + "Hierarchy architectural smells.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        List<String> targets = Arrays.asList(classNames.split("\\s*,\\s*"));
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl,
                                                            ExecutionContext ctx) {
                J.ClassDeclaration cd = super.visitClassDeclaration(classDecl, ctx);
                if (cd.getType() == null || cd.getKind() != J.ClassDeclaration.Kind.Type.Class) {
                    return cd;
                }
                boolean wanted = targets.stream()
                        .anyMatch(t -> TypeUtils.isOfClassType(cd.getType(), t));
                if (!wanted) {
                    return cd;
                }
                // already implements it? then there is nothing to do
                if (cd.getImplements() != null && cd.getImplements().stream().anyMatch(
                        i -> TypeUtils.isOfClassType(i.getType(), fullyQualifiedInterfaceName))) {
                    return cd;
                }
                return (J.ClassDeclaration) new ImplementInterface<ExecutionContext>(
                        cd, fullyQualifiedInterfaceName).visitNonNull(cd, ctx, getCursor());
            }
        };
    }
}
