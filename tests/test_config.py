from ski_terrain.config import deep_merge, feature_width_mm, set_dotted

def test_deep_merge_and_width():
    cfg = deep_merge({"printer":{"line_width_mm":0.42},"features":{"roads":{"extrusions":2}}}, {})
    assert feature_width_mm(cfg, "roads") == 0.84

def test_dotted_override():
    cfg = {}
    set_dotted(cfg, "rock.score_threshold", 0.7)
    assert cfg["rock"]["score_threshold"] == 0.7
