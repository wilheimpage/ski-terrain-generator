from pathlib import Path

from ski_terrain.simple_convert import parser


def test_parser_defaults_to_obj_and_accepts_max_dimension(tmp_path):
    output_path = tmp_path / "terrain.obj"

    args = parser().parse_args([
        "input/BX20.tif",
        "--output",
        str(output_path),
        "--max-dimension",
        "180",
    ])

    assert args.input == Path("input/BX20.tif")
    assert args.output == output_path
    assert args.format == "obj"
    assert args.max_dimension == 180.0


def test_parser_accepts_stl_format():
    args = parser().parse_args(["input/BX20.tif", "--format", "stl"])

    assert args.format == "stl"
