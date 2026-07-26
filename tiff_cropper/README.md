# TIFF Cropper

This script merges one or more GeoTIFF DEM tiles and crops them into a rotated rectangular GeoTIFF based on a JSON crop definition.

## What it does

The script:

- reads one or more input raster tiles
- merges them into a single raster
- loads a crop rectangle definition from a JSON file
- creates a rotated rectangular crop aligned to the provided geometry
- writes the result as a new GeoTIFF

It is designed for DEM or other projected raster data where the output crop must follow an exact rotated rectangle.

## Requirements

This script depends on Python packages such as:

- numpy
- rasterio
- affine

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Usage

Run the script from the project root with:

```bash
python src/tiff_cropper/src/merge-crop.py \
  --tiles data/BV21.tif data/BW21.tif \
  --crop src/tiff_cropper/crop.json \
  --output output/cropped_dem.tif
```

### Arguments

- `--tiles`: one or more input GeoTIFF files
- `--crop`: path to the JSON crop definition file
- `--output`: destination GeoTIFF path
- `--resolution`: optional output pixel size override
- `--resampling`: resampling method to use (default: bilinear)
- `--overwrite`: allow overwriting an existing output file

## Crop JSON format

The crop definition should look like this:

```json
{
  "crs": "EPSG:2193",
  "corners": {
    "top_left": [1700000, 5200000],
    "top_right": [1710000, 5200000],
    "bottom_right": [1710000, 5190000]
  }
}
```

The script uses:

- `top_left` and `top_right` to define the top edge
- `bottom_right` to define the depth and orientation of the rectangle

The bottom-left corner is then calculated automatically to form a perfect rectangle.

## Notes

- The input rasters must share the same CRS.
- The crop CRS must match the source raster CRS.
- The output will be written as a GeoTIFF with the crop geometry and metadata preserved.
