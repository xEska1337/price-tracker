from app.scraping.normalize import domain_bucket, normalize_url


def test_adds_scheme_and_lowercases_host():
    assert normalize_url("Example.COM/Path") == "https://example.com/Path"


def test_strips_tracking_params_and_fragment():
    url = "https://sklep.pl/product/1?utm_source=fb&utm_campaign=x&gclid=abc&color=red#reviews"
    assert normalize_url(url) == "https://sklep.pl/product/1?color=red"


def test_sorts_remaining_params():
    a = normalize_url("https://sklep.pl/p?b=2&a=1")
    b = normalize_url("https://sklep.pl/p?a=1&b=2")
    assert a == b == "https://sklep.pl/p?a=1&b=2"


def test_rejects_garbage():
    assert normalize_url(None) is None
    assert normalize_url("") is None
    assert normalize_url("not a url at all") is None  
    assert normalize_url("ftp://example.com/x") is None


def test_keeps_port():
    assert normalize_url("http://shop.local:8080/x") == "https://shop.local:8080/x"


def test_domain_bucket():
    assert domain_bucket("https://www.x-kom.pl/p/1") == "x-kom.pl"
    assert domain_bucket("https://morele.net:443/x") == "morele.net"
