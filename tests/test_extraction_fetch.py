"""How extraction reads a page before the model sees it (workflow.MD, "Rules one link away, fetch fixes")."""
from bs4 import BeautifulSoup

from src.collectors.extraction import content_scope, strip_page_chrome


def test_menus_and_site_header_are_stripped_but_a_sections_own_header_stays():
    soup = BeautifulSoup("<body><header>Site menu</header><nav>Home About</nav>"
                         "<section><header>Call title</header><p>Open to artists.</p></section>"
                         "<footer>Contact</footer></body>", "html.parser")
    strip_page_chrome(soup)
    assert soup.get_text(" ", strip=True) == "Call title Open to artists."


def test_a_nearly_empty_article_is_skipped_for_the_whole_page():
    filler = "The residency is for artists who have developed a promising aesthetic language. " * 5
    soup = BeautifulSoup(f"<body><p>{filler}</p><article><a>Apply here</a></article></body>", "html.parser")
    assert content_scope(soup) is soup
    soup = BeautifulSoup(f"<body><nav>Menu</nav><article><p>{filler}</p></article></body>", "html.parser")
    assert content_scope(soup).name == "article"
