package com.dsarp.recipes;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.openrewrite.ExecutionContext;
import org.openrewrite.Option;
import org.openrewrite.Recipe;
import org.openrewrite.Tree;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaVisitor;
import org.openrewrite.java.JavaParser;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.JavaType;
import org.openrewrite.java.tree.Space;
import org.openrewrite.java.tree.Statement;
import org.openrewrite.java.tree.TypeUtils;
import org.openrewrite.marker.Markers;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

/**
 * Name one numeric literal: declare it as a {@code private static final} constant and point every
 * occurrence in the class at that constant. Fowler's Replace Magic Number with Symbolic Constant,
 * and the fix for Designite's "Magic Number", which none of the 216 recipe classes in
 * rewrite-static-analysis performs.
 *
 * <p><b>The name is an option, deliberately, and the recipe will not invent one.</b> The whole
 * value of this refactoring is in the name: {@code MIN_CARD_LENGTH} says why 13 matters, while
 * {@code CONST_13} says nothing and leaves the code longer than it was. A tool that generated
 * names from values would clear the detector's count while making every site it touched worse,
 * so the caller supplies the meaning and this recipe supplies only the mechanism.
 *
 * <p>Most of what Designite flags should not reach this recipe at all. Of 68 Magic Number findings
 * in commons-validator, 49 sit in methods the maintainers marked
 * {@code // CHECKSTYLE IGNORE MagicNumber} -- they considered those literals and decided to keep
 * them -- and 14 more are 0, 1 or 2, where the digit is plainer than any name. Seven were left.
 *
 * <p>Matching is on the literal's <em>source text</em>, so {@code 0x7F} and {@code 127} are
 * different requests and the file keeps the notation its author chose. Only numeric literals are
 * considered, and only those lexically inside the named class, so a {@code 13} in a string, a
 * comment or a nested class is left alone.
 */
public class ReplaceMagicNumberWithConstant extends Recipe {

    @Option(displayName = "Class",
            description = "Fully qualified name of the class to edit.",
            example = "org.apache.commons.validator.CreditCardValidator")
    private final String fullyQualifiedClassName;

    @Option(displayName = "Literal",
            description = "The literal exactly as written in the source, so that 0x7F and 127 "
                    + "stay distinguishable.",
            example = "13")
    private final String literal;

    @Option(displayName = "Constant name",
            description = "Name for the new constant. Must say what the value MEANS; a name "
                    + "derived from the digits defeats the purpose of the refactoring.",
            example = "MIN_CARD_LENGTH")
    private final String constantName;

    @JsonCreator
    public ReplaceMagicNumberWithConstant(
            @JsonProperty("fullyQualifiedClassName") String fullyQualifiedClassName,
            @JsonProperty("literal") String literal,
            @JsonProperty("constantName") String constantName) {
        this.fullyQualifiedClassName = fullyQualifiedClassName;
        this.literal = literal;
        this.constantName = constantName;
    }

    public String getFullyQualifiedClassName() {
        return fullyQualifiedClassName;
    }

    public String getLiteral() {
        return literal;
    }

    public String getConstantName() {
        return constantName;
    }

    @Override
    public String getDisplayName() {
        return "Replace a magic number with a named constant";
    }

    @Override
    public String getDescription() {
        return "Declares one numeric literal as a private static final constant and replaces "
                + "every occurrence of it in the class. Fixes Designite's Magic Number smell. "
                + "The constant's name is supplied by the caller: a name derived from the value "
                + "would satisfy the detector while making the code worse.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        // JavaVisitor, not JavaIsoVisitor: the iso visitor requires every node to be replaced by a
        // node of its own type, and this recipe replaces a J.Literal with a J.Identifier. Under
        // JavaIsoVisitor that compiles and then dies at run time with
        // "J$Identifier cannot be cast to J$Literal" on the first file it matches.
        return new JavaVisitor<ExecutionContext>() {

            /** Set when a literal was actually replaced, so the field is added only if needed. */
            private boolean replaced;
            /** The primitive keyword of what was replaced, so the field gets the right type. */
            private String keyword = "int";

            @Override
            public J visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                boolean isTarget = classDecl.getType() != null
                        && TypeUtils.isOfClassType(classDecl.getType(), fullyQualifiedClassName);
                if (!isTarget) {
                    return super.visitClassDeclaration(classDecl, ctx);
                }
                if (declaresField(classDecl, constantName)) {
                    // Already done, or the name collides with something real. Either way, leave it:
                    // adding a second declaration would not compile.
                    return classDecl;
                }
                // Visit the body first, so `replaced` and `keyword` are known before the field is
                // built. Nothing below this point can match the literal inside the new field,
                // because the new field is added after the traversal.
                J visited = super.visitClassDeclaration(classDecl, ctx);
                if (!replaced || !(visited instanceof J.ClassDeclaration)) {
                    return visited;
                }
                J.ClassDeclaration cd = (J.ClassDeclaration) visited;
                Optional<Statement> field = constantDeclaration(ctx, keyword);
                if (!field.isPresent()) {
                    return classDecl;   // could not build it; change nothing rather than half of it
                }
                List<Statement> statements = new ArrayList<>(cd.getBody().getStatements());
                statements.add(0, field.get());
                return cd.withBody(cd.getBody().withStatements(statements));
            }

            /**
             * Swap one numeric literal for a reference to the constant.
             *
             * <p>Scoped by the enclosing class's fully qualified name, so a nested class is a
             * different class and is left alone. That matters: commons-validator's
             * {@code CreditCardValidator} has a 13 in {@code isValid}, where it is the minimum card
             * length, and another inside {@code private static class Visa}, where it is one of the
             * two lengths a Visa number may have. One name could not be right for both.
             */
            @Override
            public J visitLiteral(J.Literal lit, ExecutionContext ctx) {
                J visited = super.visitLiteral(lit, ctx);
                if (!(visited instanceof J.Literal)) {
                    return visited;
                }
                J.Literal l = (J.Literal) visited;
                J.ClassDeclaration enclosing = getCursor().firstEnclosing(J.ClassDeclaration.class);
                if (enclosing == null || enclosing.getType() == null
                        || !TypeUtils.isOfClassType(enclosing.getType(), fullyQualifiedClassName)) {
                    return l;
                }
                if (!literal.equals(l.getValueSource()) || !isNumeric(l.getType())) {
                    return l;
                }
                replaced = true;
                keyword = ((JavaType.Primitive) l.getType()).getKeyword();
                return new J.Identifier(Tree.randomId(), l.getPrefix(), Markers.EMPTY,
                        Collections.emptyList(), constantName, l.getType(), null);
            }

            private Optional<Statement> constantDeclaration(ExecutionContext ctx, String kw) {
                String src = "class DsarpConstantHolder {\n    private static final "
                        + kw + " " + constantName + " = " + literal + ";\n}\n";
                return JavaParser.fromJavaVersion().build().parse(ctx, src)
                        .filter(J.CompilationUnit.class::isInstance)
                        .map(J.CompilationUnit.class::cast)
                        .flatMap(cu -> cu.getClasses().stream())
                        .flatMap(c -> c.getBody().getStatements().stream())
                        .findFirst()
                        // One blank-line-free newline and four spaces: the field goes first in the
                        // body, where every Java style in this corpus indents by four.
                        .map(s -> s.withPrefix(Space.format("\n    ")));
            }
        };
    }

    private static boolean declaresField(J.ClassDeclaration cd, String name) {
        return cd.getBody().getStatements().stream()
                .filter(J.VariableDeclarations.class::isInstance)
                .map(J.VariableDeclarations.class::cast)
                .flatMap(vd -> vd.getVariables().stream())
                .anyMatch(v -> name.equals(v.getSimpleName()));
    }

    private static boolean isNumeric(JavaType type) {
        if (!(type instanceof JavaType.Primitive)) {
            return false;
        }
        switch ((JavaType.Primitive) type) {
            case Int:
            case Long:
            case Short:
            case Byte:
            case Double:
            case Float:
                return true;
            default:
                return false;
        }
    }
}
