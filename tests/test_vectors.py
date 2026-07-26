import numpy as np
import pandas as pd
from ski_terrain.vectors import normalise_difficulty


def test_normalise_difficulty():
    assert normalise_difficulty(" Green ", "Unclassified") == "Green"
    assert normalise_difficulty("", "Unclassified") == "Unclassified"
    assert normalise_difficulty(None, "Unclassified") == "Unclassified"
    assert normalise_difficulty(np.nan, "Unclassified") == "Unclassified"
    assert normalise_difficulty(pd.NA, "Unclassified") == "Unclassified"
