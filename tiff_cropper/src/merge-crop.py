#!/usr/bin/env python3
"""
Merge NZTM2000 DEM tiles and crop them onto a rotated rectangular grid.

The crop is defined by three points:

- top_left
- top_right
- bottom_right

The top edge is preserved exactly. The supplied bottom-right point determines
the rectangle depth, and is projected onto a line perpendicular to the top
edge. The exact bottom-right and bottom-left corners are then calculated.

Example:

    python src/merge-crop.py ^
        --tiles data/BV21.tif data/BW21.tif ^
        --crop crop.json ^
        --output output/cropped_dem.tif
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import reproject


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CropRectangle:
    """An exact rotated rectangle in projected map coordinates."""

    top_left: np.ndarray
    top_right: np.ndarray
    bottom_right: np.ndarray
    bottom_left: np.ndarray
    supplied_bottom_right: np.ndarray
    width_metres: float
    height_metres: float
    bottom_right_adjustment_metres: float
    bottom_right_along_edge_error_metres: float

    @property
    def top_vector(self) -> np.ndarray:
        return self.top_right - self.top_left

    @property
    def left_vector(self) -> np.ndarray:
        return self.bottom_left - self.top_left

    @property
    def top_unit_vector(self) -> np.ndarray:
        return self.top_vector / self.width_metres

    @property
    def left_unit_vector(self) -> np.ndarray:
        return self.left_vector / self.height_metres

    def validate(self, tolerance_metres: float = 0.01) -> None:
        """Confirm that the calculated coordinates form an exact rectangle."""
        if self.width_metres <= 0:
            raise ValueError("Crop width must be greater than zero.")

        if self.height_metres <= 0:
            raise ValueError("Crop height must be greater than zero.")

        expected_bottom_right = (
            self.top_left
            + self.top_vector
            + self.left_vector
        )

        closure_error = float(
            np.linalg.norm(
                self.bottom_right - expected_bottom_right
            )
        )

        if closure_error > tolerance_metres:
            raise ValueError(
                "The crop corners do not close as a rectangle. "
                f"Closure error: {closure_error:.6f} m."
            )

        dot_product = float(
            np.dot(
                self.top_vector,
                self.left_vector,
            )
        )

        perpendicular_tolerance = (
            tolerance_metres
            * max(
                self.width_metres,
                self.height_metres,
            )
        )

        if abs(dot_product) > perpendicular_tolerance:
            raise ValueError(
                "The calculated crop sides are not perpendicular. "
                f"Dot product: {dot_product:.6f}."
            )

    def as_tag_values(self) -> dict[str, str]:
        """Return crop details suitable for GeoTIFF metadata tags."""
        return {
            "top_left": self._format_coordinate(self.top_left),
            "top_right": self._format_coordinate(self.top_right),
            "bottom_right": self._format_coordinate(
                self.bottom_right
            ),
            "bottom_left": self._format_coordinate(
                self.bottom_left
            ),
            "supplied_bottom_right": self._format_coordinate(
                self.supplied_bottom_right
            ),
            "crop_width_metres": f"{self.width_metres:.6f}",
            "crop_height_metres": f"{self.height_metres:.6f}",
            "bottom_right_adjustment_metres": (
                f"{self.bottom_right_adjustment_metres:.6f}"
            ),
            "bottom_right_along_edge_error_metres": (
                f"{self.bottom_right_along_edge_error_metres:.6f}"
            ),
        }

    @staticmethod
    def _format_coordinate(coordinate: np.ndarray) -> str:
        return f"{coordinate[0]:.3f},{coordinate[1]:.3f}"


@dataclass(frozen=True)
class CropConfiguration:
    """Crop file settings loaded from JSON."""

    crs: rasterio.crs.CRS
    rectangle: CropRectangle


class TerrainCrop:
    """
    Merge DEM tiles and create a rotated rectangular GeoTIFF crop.

    This class currently handles only the DEM merge and crop stage. Later
    terrain-analysis stages can be added as separate classes without growing
    the command-line main function indefinitely.
    """

    def __init__(
        self,
        tile_paths: Sequence[Path],
        crop_path: Path,
        output_path: Path,
        resolution: float | None = None,
        resampling: Resampling = Resampling.bilinear,
        overwrite: bool = False,
    ) -> None:
        self.tile_paths = list(tile_paths)
        self.crop_path = crop_path
        self.output_path = output_path
        self.requested_resolution = resolution
        self.resampling = resampling
        self.overwrite = overwrite

        self.crop_configuration: CropConfiguration | None = None

    def run(self) -> None:
        """Execute the complete merge-and-crop process."""
        self._validate_paths()

        self.crop_configuration = self._load_crop_configuration()
        self.crop_configuration.rectangle.validate()

        self._log_rectangle()

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with ExitStack() as stack:
            sources = [
                stack.enter_context(rasterio.open(path))
                for path in self.tile_paths
            ]

            self._validate_sources(sources)

            first_source = sources[0]
            source_crs = first_source.crs

            if source_crs is None:
                raise ValueError(
                    "The first source raster has no CRS."
                )

            if source_crs != self.crop_configuration.crs:
                raise ValueError(
                    "Crop CRS does not match the source raster CRS: "
                    f"{self.crop_configuration.crs} != {source_crs}"
                )

            nodata = self._get_nodata_value(first_source)
            resolution = self._get_output_resolution(first_source)

            LOGGER.info(
                "Merging %d source tile(s)",
                len(sources),
            )

            mosaic, mosaic_transform = merge(
                sources,
                nodata=nodata,
                dtype="float32",
            )

            source_dem = mosaic[0]

            destination, output_transform = self._create_rotated_crop(
                source_dem=source_dem,
                source_transform=mosaic_transform,
                source_crs=source_crs,
                nodata=nodata,
                resolution=resolution,
            )

            self._write_output(
                destination=destination,
                output_transform=output_transform,
                source_crs=source_crs,
                nodata=nodata,
                first_source=first_source,
                resolution=resolution,
            )

        LOGGER.info("Finished successfully")

    def _validate_paths(self) -> None:
        missing_tiles = [
            str(path)
            for path in self.tile_paths
            if not path.is_file()
        ]

        if missing_tiles:
            raise FileNotFoundError(
                "The following input tiles do not exist:\n"
                + "\n".join(
                    f"  {path}"
                    for path in missing_tiles
                )
            )

        if not self.crop_path.is_file():
            raise FileNotFoundError(
                f"Crop file does not exist: {self.crop_path}"
            )

        if self.output_path.exists() and not self.overwrite:
            raise FileExistsError(
                f"Output already exists: {self.output_path}\n"
                "Use --overwrite to replace it."
            )

        if (
            self.requested_resolution is not None
            and self.requested_resolution <= 0
        ):
            raise ValueError(
                "Output resolution must be greater than zero."
            )

    def _load_crop_configuration(self) -> CropConfiguration:
        with self.crop_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        try:
            crs = rasterio.crs.CRS.from_string(
                str(data["crs"])
            )

            raw_corners = data["corners"]

            top_left = self._parse_coordinate(
                raw_corners["top_left"],
                "top_left",
            )

            top_right = self._parse_coordinate(
                raw_corners["top_right"],
                "top_right",
            )

            supplied_bottom_right = self._parse_coordinate(
                raw_corners["bottom_right"],
                "bottom_right",
            )

        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Invalid crop file. Expected a CRS and three "
                "coordinates named top_left, top_right, and "
                "bottom_right."
            ) from error

        rectangle = self._construct_rectangle(
            top_left=top_left,
            top_right=top_right,
            supplied_bottom_right=supplied_bottom_right,
        )

        return CropConfiguration(
            crs=crs,
            rectangle=rectangle,
        )

    @staticmethod
    def _parse_coordinate(
        value: object,
        name: str,
    ) -> np.ndarray:
        coordinate = np.asarray(
            value,
            dtype=np.float64,
        )

        if coordinate.shape != (2,):
            raise ValueError(
                f"Corner {name!r} must contain exactly two numbers."
            )

        if not np.all(np.isfinite(coordinate)):
            raise ValueError(
                f"Corner {name!r} must contain finite numbers."
            )

        return coordinate

    @staticmethod
    def _construct_rectangle(
        top_left: np.ndarray,
        top_right: np.ndarray,
        supplied_bottom_right: np.ndarray,
    ) -> CropRectangle:
        """
        Construct an exact rectangle from three supplied points.

        The top-left and top-right coordinates define the fixed top edge.

        The vector from top-right to the supplied bottom-right coordinate is
        projected onto a perpendicular to the top edge. The along-edge
        component is discarded, leaving an exact 90-degree side.
        """
        top_vector = top_right - top_left
        width = float(np.linalg.norm(top_vector))

        if width <= 0:
            raise ValueError(
                "Top-left and top-right must be different coordinates."
            )

        top_unit = top_vector / width

        perpendicular_a = np.array(
            [
                top_unit[1],
                -top_unit[0],
            ],
            dtype=np.float64,
        )

        perpendicular_b = -perpendicular_a

        supplied_side_vector = (
            supplied_bottom_right - top_right
        )

        projection_a = float(
            np.dot(
                supplied_side_vector,
                perpendicular_a,
            )
        )

        projection_b = float(
            np.dot(
                supplied_side_vector,
                perpendicular_b,
            )
        )

        if projection_a >= projection_b:
            down_unit = perpendicular_a
            height = projection_a
        else:
            down_unit = perpendicular_b
            height = projection_b

        if height <= 0:
            raise ValueError(
                "The supplied bottom-right coordinate does not "
                "define a positive rectangle depth."
            )

        side_vector = down_unit * height

        exact_bottom_right = top_right + side_vector
        exact_bottom_left = top_left + side_vector

        adjustment_distance = float(
            np.linalg.norm(
                exact_bottom_right
                - supplied_bottom_right
            )
        )

        along_edge_error = float(
            np.dot(
                supplied_side_vector,
                top_unit,
            )
        )

        return CropRectangle(
            top_left=top_left,
            top_right=top_right,
            bottom_right=exact_bottom_right,
            bottom_left=exact_bottom_left,
            supplied_bottom_right=supplied_bottom_right,
            width_metres=width,
            height_metres=height,
            bottom_right_adjustment_metres=(
                adjustment_distance
            ),
            bottom_right_along_edge_error_metres=(
                along_edge_error
            ),
        )

    def _validate_sources(
        self,
        sources: Sequence[rasterio.io.DatasetReader],
    ) -> None:
        if not sources:
            raise ValueError(
                "At least one source raster is required."
            )

        first = sources[0]

        if first.count < 1:
            raise ValueError(
                f"Input raster has no bands: {self.tile_paths[0]}"
            )

        if first.crs is None:
            raise ValueError(
                f"Input raster has no CRS: {self.tile_paths[0]}"
            )

        for path, source in zip(
            self.tile_paths,
            sources,
            strict=True,
        ):
            if source.crs != first.crs:
                raise ValueError(
                    f"CRS mismatch in {path}: "
                    f"{source.crs} != {first.crs}"
                )

            if source.count != first.count:
                raise ValueError(
                    f"Band-count mismatch in {path}: "
                    f"{source.count} != {first.count}"
                )

    @staticmethod
    def _get_nodata_value(
        source: rasterio.io.DatasetReader,
    ) -> float:
        nodata = source.nodata

        if nodata is None:
            nodata = -9999.0

            LOGGER.warning(
                "No source NoData value was defined; using %.1f",
                nodata,
            )

        return float(nodata)

    def _get_output_resolution(
        self,
        source: rasterio.io.DatasetReader,
    ) -> float:
        if self.requested_resolution is not None:
            return self.requested_resolution

        source_x_resolution = abs(
            float(source.transform.a)
        )

        source_y_resolution = abs(
            float(source.transform.e)
        )

        return min(
            source_x_resolution,
            source_y_resolution,
        )

    def _create_rotated_crop(
        self,
        source_dem: np.ndarray,
        source_transform: Affine,
        source_crs: rasterio.crs.CRS,
        nodata: float,
        resolution: float,
    ) -> tuple[np.ndarray, Affine]:
        configuration = self._require_crop_configuration()
        rectangle = configuration.rectangle

        output_width = max(
            1,
            math.ceil(
                rectangle.width_metres / resolution
            ),
        )

        output_height = max(
            1,
            math.ceil(
                rectangle.height_metres / resolution
            ),
        )

        horizontal_pixel_size = (
            rectangle.width_metres / output_width
        )

        vertical_pixel_size = (
            rectangle.height_metres / output_height
        )

        output_transform = Affine(
            rectangle.top_unit_vector[0]
            * horizontal_pixel_size,
            rectangle.left_unit_vector[0]
            * vertical_pixel_size,
            rectangle.top_left[0],
            rectangle.top_unit_vector[1]
            * horizontal_pixel_size,
            rectangle.left_unit_vector[1]
            * vertical_pixel_size,
            rectangle.top_left[1],
        )

        destination = np.full(
            (
                output_height,
                output_width,
            ),
            nodata,
            dtype=np.float32,
        )

        LOGGER.info(
            "Creating rotated crop: %.2f m x %.2f m",
            rectangle.width_metres,
            rectangle.height_metres,
        )

        LOGGER.info(
            "Output raster: %d columns x %d rows",
            output_width,
            output_height,
        )

        LOGGER.info(
            "Pixel dimensions: %.6f m x %.6f m",
            horizontal_pixel_size,
            vertical_pixel_size,
        )

        reproject(
            source=source_dem,
            destination=destination,
            src_transform=source_transform,
            src_crs=source_crs,
            src_nodata=nodata,
            dst_transform=output_transform,
            dst_crs=source_crs,
            dst_nodata=nodata,
            resampling=self.resampling,
            num_threads=2,
            init_dest_nodata=True,
        )

        valid_pixels = self._get_valid_mask(
            destination,
            nodata,
        )

        if not np.any(valid_pixels):
            raise RuntimeError(
                "The crop contains no valid elevation pixels. "
                "Check the coordinates and source tiles."
            )

        valid_count = int(
            np.count_nonzero(valid_pixels)
        )

        total_count = int(destination.size)

        coverage = (
            valid_count
            / total_count
            * 100.0
        )

        minimum_elevation = float(
            destination[valid_pixels].min()
        )

        maximum_elevation = float(
            destination[valid_pixels].max()
        )

        LOGGER.info(
            "Valid-data coverage: %.2f%%",
            coverage,
        )

        LOGGER.info(
            "Elevation range: %.3f m to %.3f m",
            minimum_elevation,
            maximum_elevation,
        )

        if coverage < 100.0:
            LOGGER.warning(
                "%.2f%% of the output crop contains no source data.",
                100.0 - coverage,
            )

        return destination, output_transform

    def _write_output(
        self,
        destination: np.ndarray,
        output_transform: Affine,
        source_crs: rasterio.crs.CRS,
        nodata: float,
        first_source: rasterio.io.DatasetReader,
        resolution: float,
    ) -> None:
        configuration = self._require_crop_configuration()
        rectangle = configuration.rectangle

        output_height, output_width = destination.shape

        horizontal_pixel_size = (
            rectangle.width_metres / output_width
        )

        vertical_pixel_size = (
            rectangle.height_metres / output_height
        )

        profile = first_source.profile.copy()

        profile.update(
            driver="GTiff",
            width=output_width,
            height=output_height,
            count=1,
            dtype="float32",
            crs=source_crs,
            transform=output_transform,
            nodata=nodata,
            compress="deflate",
            predictor=3,
            tiled=True,
            blockxsize=256,
            blockysize=256,
            BIGTIFF="IF_SAFER",
        )

        LOGGER.info(
            "Writing %s",
            self.output_path,
        )

        with rasterio.open(
            self.output_path,
            "w",
            **profile,
        ) as output:
            output.write(
                destination,
                1,
            )

            output.set_band_description(
                1,
                "Elevation",
            )

            tags = {
                "crop_type": "rotated_rectangle",
                "requested_resolution_metres": (
                    f"{resolution:.6f}"
                ),
                "horizontal_pixel_size_metres": (
                    f"{horizontal_pixel_size:.9f}"
                ),
                "vertical_pixel_size_metres": (
                    f"{vertical_pixel_size:.9f}"
                ),
                "source_tiles": ";".join(
                    path.name
                    for path in self.tile_paths
                ),
            }

            tags.update(
                rectangle.as_tag_values()
            )

            output.update_tags(**tags)

    def _log_rectangle(self) -> None:
        configuration = self._require_crop_configuration()
        rectangle = configuration.rectangle

        LOGGER.info(
            "Calculated rectangle corners:"
        )

        LOGGER.info(
            "  Top left:     %.3f, %.3f",
            rectangle.top_left[0],
            rectangle.top_left[1],
        )

        LOGGER.info(
            "  Top right:    %.3f, %.3f",
            rectangle.top_right[0],
            rectangle.top_right[1],
        )

        LOGGER.info(
            "  Bottom right: %.3f, %.3f",
            rectangle.bottom_right[0],
            rectangle.bottom_right[1],
        )

        LOGGER.info(
            "  Bottom left:  %.3f, %.3f",
            rectangle.bottom_left[0],
            rectangle.bottom_left[1],
        )

        LOGGER.info(
            "Rectangle dimensions: %.2f m x %.2f m",
            rectangle.width_metres,
            rectangle.height_metres,
        )

        LOGGER.info(
            "Supplied bottom-right adjusted by %.3f m",
            rectangle.bottom_right_adjustment_metres,
        )

        LOGGER.info(
            "Discarded along-edge error: %.3f m",
            rectangle.bottom_right_along_edge_error_metres,
        )

    def _require_crop_configuration(
        self,
    ) -> CropConfiguration:
        if self.crop_configuration is None:
            raise RuntimeError(
                "Crop configuration has not been loaded."
            )

        return self.crop_configuration

    @staticmethod
    def _get_valid_mask(
        data: np.ndarray,
        nodata: float,
    ) -> np.ndarray:
        if math.isnan(nodata):
            return np.isfinite(data)

        return (
            np.isfinite(data)
            & (data != nodata)
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge DEM GeoTIFF tiles and crop them to a rotated "
            "rectangle defined by three coordinates."
        )
    )

    parser.add_argument(
        "--tiles",
        nargs="+",
        required=True,
        type=Path,
        help="Input DEM GeoTIFF files.",
    )

    parser.add_argument(
        "--crop",
        required=True,
        type=Path,
        help="JSON file containing the three crop coordinates.",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output cropped GeoTIFF.",
    )

    parser.add_argument(
        "--resolution",
        type=float,
        default=None,
        help=(
            "Output pixel size in metres. "
            "Defaults to the input raster resolution."
        ),
    )

    parser.add_argument(
        "--resampling",
        choices=(
            "nearest",
            "bilinear",
            "cubic",
        ),
        default="bilinear",
        help="Resampling method. Default: bilinear.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file.",
    )

    return parser.parse_args()


def get_resampling_method(
    name: str,
) -> Resampling:
    methods = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }

    return methods[name]


def main() -> None:
    args = parse_arguments()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    processor = TerrainCrop(
        tile_paths=args.tiles,
        crop_path=args.crop,
        output_path=args.output,
        resolution=args.resolution,
        resampling=get_resampling_method(
            args.resampling
        ),
        overwrite=args.overwrite,
    )

    processor.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from error