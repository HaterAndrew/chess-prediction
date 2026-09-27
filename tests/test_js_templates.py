"""pipeline/js_templates.py: template literals survive minification.

rjsmin 1.2.5 strips the spaces in a template literal nested inside another's
${...}; the live hero caption read "80%range" and attributes ran together.
The bundler hides every template behind a placeholder while rjsmin runs.
"""
import pytest
import rjsmin

from pipeline import js_templates as J


def _roundtrip(src):
    code, literals = J.protect(src)
    return J.restore(rjsmin.jsmin(code), literals)


def test_rjsmin_alone_still_breaks_a_nested_template():
    # If this starts passing, rjsmin fixed it upstream and the guard can go.
    assert "}%range" in rjsmin.jsmin("const a = `${b ? `${n}% range` : ''}`;")


def test_a_nested_template_keeps_its_spaces():
    out = _roundtrip("const a = `x ${b ? ` (80% range ${c} to ${d})` : ''} y`;")
    assert "` (80% range ${c} to ${d})`" in out


def test_attributes_keep_the_space_between_them():
    out = _roundtrip("h = `<i ${f ? `<b class=\"a\" id=\"${f}\"></b>` : ''}>`;")
    assert 'class="a" id="${f}"' in out


def test_backticks_in_strings_comments_and_regexes_are_not_templates():
    src = ("const s = 'a`b'; const t = \"c`d\"; // e`f\n"
           "/* g`h */ const r = /`/.test(s); function f(x) { return /i`j/.test(x); }")
    assert J.template_spans(src) == []
    assert _roundtrip(src) == rjsmin.jsmin(src)


def test_a_slash_after_a_value_divides():
    src = "const q = total / 2 / n; const w = `${q} / ${n}`;"
    spans = J.template_spans(src)
    assert [src[a:b] for a, b in spans] == ["`${q} / ${n}`"]


def test_braces_and_strings_inside_an_expression_do_not_end_it():
    src = "x = `a ${ {k: '}'}.k } b ${`c ${'`'} d`} e`;"
    (a, b), = J.template_spans(src)
    assert src[a:b] == src[4:-1]


def test_restore_refuses_a_lost_placeholder():
    with pytest.raises(ValueError):
        J.restore("const a = 1;", ["`x`"])


def test_an_unterminated_template_is_an_error():
    with pytest.raises(ValueError):
        J.template_spans("const a = `oops")
