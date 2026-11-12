from app.rss.parse import parse_feed

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:media="http://search.yahoo.com/mrss/" xmlns:pepper="http://www.pepper.com/rss" version="2.0">
<channel><title>Pepper.pl</title>
<item>
  <category><![CDATA[Moda]]></category>
  <pepper:merchant name="Picksport" price="110z&#322;"/>
  <media:content medium="image" url="https://static.pepper.pl/img/a.jpg" width="100" height="100"/>
  <title><![CDATA[Buty ADIDAS ULTIMASHOW 2.0 - 24,99 euro]]></title>
  <description><![CDATA[<strong>110zł - Picksport</strong><br /><img src="https://static.pepper.pl/img/a.jpg"/><p>rozmiar 42-47<br />Przewiewna cholewka.</p>]]></description>
  <link>https://www.pepper.pl/promocja/buty-adidas-1</link>
  <guid isPermaLink="false">https://www.pepper.pl/promocja/buty-adidas-1</guid>
  <pubDate>Tue, 11 Nov 2026 18:30:00 +0000</pubDate>
</item>
<item>
  <media:content medium="image" url="https://static.pepper.pl/img/b.jpg"/>
  <title>Monitor 27 cali 165Hz</title>
  <description><strong>799zł - x-kom</strong> odświeżony model</description>
  <link>https://www.pepper.pl/promocja/monitor-2</link>
  <pubDate>Tue, 11 Nov 2026 20:00:00 +0000</pubDate>
</item>
</channel></rss>\n""".encode("utf-8")


def test_parse_feed_full_extension():
    items = parse_feed(SAMPLE_FEED)
    assert len(items) == 2
    first = [i for i in items if "adidas" in i["link"]][0]
    assert first["title"].startswith("Buty ADIDAS")
    assert first["merchant"] == "Picksport"
    assert first["price_raw"] == "110zł"
    assert first["image_url"] == "https://static.pepper.pl/img/a.jpg"
    assert first["category"] == "Moda"
    assert first["external_id"] == "https://www.pepper.pl/promocja/buty-adidas-1"
    assert first["published_at"].year == 2026
    assert first["published_at"].utcoffset().total_seconds() == 0
    assert "<" not in first["snippet"]
    assert "rozmiar 42-47" in first["snippet"]


def test_parse_feed_merchant_fallback_from_description():
    items = parse_feed(SAMPLE_FEED)
    monitor = [i for i in items if "monitor" in i["link"]][0]
    assert monitor["merchant"] == "x-kom"
    assert monitor["price_raw"] == "799zł"
    assert monitor["category"] is None
    assert monitor["image_url"] == "https://static.pepper.pl/img/b.jpg"
