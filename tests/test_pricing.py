from app.scraping.pricing import guess_currency, parse_price_number


def test_pln_comma_decimal_with_thin_spaces():
    assert parse_price_number("1\u00a0234,56\u00a0z\u0142") == 1234.56
    assert parse_price_number("1 234,56 zł") == 1234.56


def test_dot_decimal_with_comma_thousands():
    assert parse_price_number("1,234.56") == 1234.56


def test_dollar_and_plain():
    assert parse_price_number("$99.90") == 99.90
    assert parse_price_number(123) == 123.0
    assert parse_price_number("59") == 59.0


def test_comma_only_three_digits_is_thousands():
    assert parse_price_number("1,234") == 1234.0


def test_comma_only_two_digits_is_decimal():
    assert parse_price_number("12,34") == 12.34


def test_junk_and_bounds():
    assert parse_price_number("cena") is None
    assert parse_price_number("") is None
    assert parse_price_number(None) is None
    assert parse_price_number("0") is None
    assert parse_price_number("-12") is None
    assert parse_price_number("99999999999") is None


def test_guess_currency():
    assert guess_currency("110zł") == "PLN"
    assert guess_currency("24,99 euro") is None
    assert guess_currency("€10") == "EUR"
    assert guess_currency(None, default="PLN") == "PLN"
