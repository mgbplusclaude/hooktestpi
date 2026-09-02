"""The table renderer that replaced prettytable."""

from hooktestpi.console import Table, magenta, supports_color


def test_table_renders_headers_and_rows():
    table = Table(["A", "B"])
    table.add_row(["1", "2"])
    rendered = str(table)
    assert "| A " in rendered
    assert rendered.count("+---") >= 1
    # header rule, header, rule, row, rule
    assert len(rendered.splitlines()) == 5


def test_table_handles_multiline_cells():
    table = Table(["Name", "Errors"])
    table.add_row(["x.xml", "one\ntwo"])
    lines = str(table).splitlines()
    assert any("one" in line for line in lines)
    assert any("two" in line for line in lines)


def test_table_rejects_wrong_width():
    table = Table(["A", "B"])
    try:
        table.add_row(["only one"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_combining_accents_do_not_widen_columns():
    """Greek in NFD carries combining marks that occupy no terminal cell."""
    table = Table(["x"])
    table.add_row(["á"])          # a + combining acute
    plain = Table(["x"])
    plain.add_row(["a"])
    assert len(str(table).splitlines()[0]) == len(str(plain).splitlines()[0])


def test_colour_is_opt_out():
    assert magenta("x", force=False) == "x"
    assert magenta("x", force=True) != "x"
    assert isinstance(supports_color(), bool)
