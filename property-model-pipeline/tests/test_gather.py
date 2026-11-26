from propmodel.gather import parse_address, matches, gallery


def test_parse_and_match():
    a = parse_address("123 N Main St, Ames, IA 50010")
    assert a.key == "123 n main st" and a.state == "IA" and a.zip == "50010"
    assert matches("https://www.zillow.com/homedetails/123-N-Main-St-Ames-IA-50010/1_zpid/", a)
    assert matches("https://www.realtor.com/realestateandhomes-detail/123-N-Main-St_Ames_IA_50010_M1", a)
    assert not matches("https://www.zillow.com/homedetails/125-N-Main-St-Ames-IA-50010/2_zpid/", a)
    assert not matches("https://www.example-listings.com/homes/123-N-ELM-ST-AMES-IA-50010/3", a)


def test_gallery_keeps_first_run_only():
    own = "".join(f"![p](https://photos.example.com/fp/{i:032x}-cc_ft_960.jpg) caption {'x' * 60}\n" for i in range(5))
    nearby = "x" * 2000 + "".join(f"![n](https://photos.example.com/fp/{i + 100:032x}-p_c.jpg)\n" for i in range(3))
    g = gallery("header " + own + nearby)
    assert len(g) == 5 and all("cc_ft_960" in u for u in g)
