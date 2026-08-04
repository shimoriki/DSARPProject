package com.dsarp.recipes;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.openrewrite.ExecutionContext;
import org.openrewrite.Option;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.ExtractInterface;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeUtils;

/**
 * Extract an interface from a concrete class — the seam needed for Dependency Inversion.
 *
 * <p>rewrite-java contains the machinery ({@code ExtractInterface.CreateInterface}) but only
 * as a {@link JavaIsoVisitor}: it is not a {@link Recipe}, so it cannot be named from a
 * declarative {@code rewrite.yml}. This wrapper exposes it, which is what lets DSARP address
 * smells that need a NEW type rather than a relocation — intra-package class cycles,
 * Rebellious Hierarchy, and unstable dependencies where moving classes is not an option.
 */
public class ExtractInterfaceForClass extends Recipe {

    @Option(displayName = "Class",
            description = "Fully qualified name of the class to extract an interface from.",
            example = "com.example.Service")
    private final String fullyQualifiedClassName;

    @Option(displayName = "Interface",
            description = "Fully qualified name of the interface to create.",
            example = "com.example.ServiceApi")
    private final String fullyQualifiedInterfaceName;

    @JsonCreator
    public ExtractInterfaceForClass(
            @JsonProperty("fullyQualifiedClassName") String fullyQualifiedClassName,
            @JsonProperty("fullyQualifiedInterfaceName") String fullyQualifiedInterfaceName) {
        this.fullyQualifiedClassName = fullyQualifiedClassName;
        this.fullyQualifiedInterfaceName = fullyQualifiedInterfaceName;
    }

    public String getFullyQualifiedClassName() {
        return fullyQualifiedClassName;
    }

    public String getFullyQualifiedInterfaceName() {
        return fullyQualifiedInterfaceName;
    }

    @Override
    public String getDisplayName() {
        return "Extract interface from a class";
    }

    @Override
    public String getDescription() {
        return "Creates an interface declaring the public methods of the given class, and makes "
                + "the class implement it. Provides the abstraction seam required to invert a "
                + "dependency, which relocation-based refactorings cannot do.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl,
                                                            ExecutionContext ctx) {
                J.ClassDeclaration cd = classDecl;

                // rewrite-java's CreateInterface copies the source type's `extends` clause
                // onto the generated interface. `interface X extends SomeClass` is illegal
                // Java ("interface expected here"), which made this recipe unusable on any
                // class with a superclass - i.e. most of the ones worth extracting from.
                // The interface only needs the method signatures, so the clause is dropped.
                if (cd.getKind() == J.ClassDeclaration.Kind.Type.Interface
                        && cd.getExtends() != null
                        && cd.getType() != null
                        && TypeUtils.isOfClassType(cd.getType(), fullyQualifiedInterfaceName)) {
                    return cd.withExtends(null);
                }

                if (cd.getType() == null
                        || !TypeUtils.isOfClassType(cd.getType(), fullyQualifiedClassName)) {
                    return cd;
                }
                doAfterVisit(new ExtractInterface.CreateInterface(fullyQualifiedInterfaceName));
                return cd;
            }
        };
    }
}
