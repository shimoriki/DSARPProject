package com.dsarp.recipes;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.openrewrite.ExecutionContext;
import org.openrewrite.Option;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeUtils;

import java.util.ArrayList;
import java.util.List;

/**
 * Make one field {@code private} — the fix for Designite's "Deficient Encapsulation".
 *
 * <p>rewrite-java ships {@code ChangeMethodAccessLevel} but has no field equivalent, so this
 * is the transformation DSARP could not express with stock recipes.
 *
 * <p>Narrowing visibility only compiles when nothing outside the declaring class reads the
 * field. DSARP checks that from the source index before it ever emits this recipe, so the
 * recipe itself stays deliberately simple and does not attempt to rewrite call sites.
 */
public class ReduceFieldVisibility extends Recipe {

    @Option(displayName = "Class",
            description = "Fully qualified name of the class declaring the field.",
            example = "com.example.Service")
    private final String fullyQualifiedClassName;

    @Option(displayName = "Field",
            description = "Name of the field whose visibility should be narrowed.",
            example = "cache")
    private final String fieldName;

    @JsonCreator
    public ReduceFieldVisibility(
            @JsonProperty("fullyQualifiedClassName") String fullyQualifiedClassName,
            @JsonProperty("fieldName") String fieldName) {
        this.fullyQualifiedClassName = fullyQualifiedClassName;
        this.fieldName = fieldName;
    }

    public String getFullyQualifiedClassName() {
        return fullyQualifiedClassName;
    }

    public String getFieldName() {
        return fieldName;
    }

    @Override
    public String getDisplayName() {
        return "Reduce field visibility to private";
    }

    @Override
    public String getDescription() {
        return "Changes a public or protected field to private. Fixes the Deficient "
                + "Encapsulation architectural smell. Only safe when no code outside the "
                + "declaring class reads the field; DSARP verifies that before applying it.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.VariableDeclarations visitVariableDeclarations(J.VariableDeclarations multiVariable,
                                                                    ExecutionContext ctx) {
                J.VariableDeclarations vd = super.visitVariableDeclarations(multiVariable, ctx);

                J.ClassDeclaration enclosing = getCursor().firstEnclosing(J.ClassDeclaration.class);
                if (enclosing == null || enclosing.getType() == null
                        || !TypeUtils.isOfClassType(enclosing.getType(), fullyQualifiedClassName)) {
                    return vd;
                }
                // only the requested field, and only real fields (the cursor parent is the class body)
                boolean matches = vd.getVariables().stream()
                        .anyMatch(v -> fieldName.equals(v.getSimpleName()));
                if (!matches) {
                    return vd;
                }
                boolean alreadyPrivate = vd.getModifiers().stream()
                        .anyMatch(m -> m.getType() == J.Modifier.Type.Private);
                if (alreadyPrivate) {
                    return vd;
                }

                List<J.Modifier> updated = new ArrayList<>();
                boolean replaced = false;
                for (J.Modifier m : vd.getModifiers()) {
                    if (m.getType() == J.Modifier.Type.Public
                            || m.getType() == J.Modifier.Type.Protected) {
                        // reuse the original modifier's formatting so spacing stays intact
                        updated.add(m.withType(J.Modifier.Type.Private));
                        replaced = true;
                    } else {
                        updated.add(m);
                    }
                }
                if (!replaced) {
                    return vd;   // package-private already; nothing public to narrow
                }
                return vd.withModifiers(updated);
            }
        };
    }
}
