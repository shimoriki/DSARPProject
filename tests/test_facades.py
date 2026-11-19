"""Facade source from javap text, for each kind of moved class."""
from dsarp.refactoring.facades import facade_source

H = "/* license */\n"


def test_subclass_keeps_generics_and_constructors():
    javap = ('Compiled from "Box.java"\n'
             "public abstract class a.b.Box<K, V extends java.lang.Comparable<V>> implements java.io.Serializable {\n"
             "  public static final int SIZE;\n"
             "  public a.b.Box();\n"
             "  protected <T> a.b.Box(java.util.Map<K, V>, T...) throws java.io.IOException;\n"
             "  public abstract V get(K);\n"
             "}\n")
    src, kind = facade_source(H, "a.b.Box", "a.c.Box", javap)
    assert kind == "subclass"
    assert src.startswith(H + "package a.b;\n")
    assert "public abstract class Box<K, V extends java.lang.Comparable<V>> extends a.c.Box<K, V> {" in src
    assert "protected <T> Box(java.util.Map<K, V> p0, T... p1) throws java.io.IOException {" in src
    assert "super(p0, p1);" in src
    assert "@Deprecated" in src and "SIZE" not in src     # inherited through the superclass


def test_final_utility_class_delegates_statics():
    javap = ('Compiled from "Util.java"\n'
             "public final class a.b.Util {\n"
             "  public static final java.lang.String NAME;\n"
             "  public static <T> java.util.List<T> of(T...);\n"
             "  public static void run(a.b.Util$Job);\n"
             "  public static a.b.Util$Job job(x.a.b.Util);\n"
             "}\n")
    src, kind = facade_source(H, "a.b.Util", "a.c.Util", javap)
    assert kind == "statics"
    assert "public static final java.lang.String NAME = a.c.Util.NAME;" in src
    assert "public static <T> java.util.List<T> of(T... p0) {\n        return a.c.Util.of(p0);" in src
    # Nested types go by the new name, as the facade declares none; other packages are left alone.
    assert "public static void run(a.c.Util.Job p0) {\n        a.c.Util.run(p0);" in src
    assert "public static a.c.Util.Job job(x.a.b.Util p0) {" in src


def test_interface_redeclares_statics():
    javap = ('Compiled from "Api.java"\n'
             "public interface a.b.Api {\n"
             "  public static a.b.Api none();\n"
             "  public abstract void call();\n"
             "}\n")
    src, kind = facade_source(H, "a.b.Api", "a.c.Api", javap)
    assert kind == "interface"
    assert "public interface Api extends a.c.Api {" in src
    assert "return a.c.Api.none();" in src


def test_facade_first_measures_again_only_when_facades_broke_build_or_cycle():
    from dsarp.experiments.scc_dissolve import facade_first
    calls = []

    def once(gate):
        def run(plan_, fac):
            calls.append(fac)
            if fac:
                return {"facades": [{"kind": "subclass"}], "level": "2", "measured_left": 2,
                        "verdict": {"accepted": False, "failed_gate": gate, "why": "cycle"}}
            return {"level": "4c", "verdict": {"accepted": True}}
        return run

    r = facade_first(once("structural"), {})
    assert calls == [True, False] and r["level"] == "4c"
    assert r["facade_fallback"]["failed_gate"] == "structural" and r["facade_fallback"]["level"] == "2"
    calls.clear()
    r = facade_first(once("behavioural"), {})          # a test failure is not the facade's edge
    assert calls == [True] and "facade_fallback" not in r


def test_enums_and_package_private_get_no_facade():
    enum = 'Compiled from "E.java"\npublic final class a.b.E extends java.lang.Enum<a.b.E> {\n}\n'
    hidden = 'Compiled from "H.java"\nclass a.b.H {\n}\n'
    assert facade_source(H, "a.b.E", "a.c.E", enum)[0] is None
    assert facade_source(H, "a.b.H", "a.c.H", hidden)[0] is None
