from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def save_preview(path: Path, title: str, valid, rock, masks, slope, dzdx, dzdy, score=None, diagnostics=False):
    rgb = np.zeros((*valid.shape, 3), dtype=np.float32)
    rgb[:] = (0.92, 0.94, 0.97)
    rgb[rock] = (0.42, 0.42, 0.42)
    rgb[masks["forest"]] = (0.16, 0.48, 0.18)
    rgb[masks["roads"]] = (0.52, 0.52, 0.52)

    # Preview colours are visual aids only; exported objects carry names, not a
    # required filament assignment. The colormap scales to any number of classes.
    run_items = list(masks["runs"].items())
    cmap = plt.get_cmap("tab20", max(1, len(run_items)))
    for index, (_, mask) in enumerate(run_items):
        rgb[mask] = np.asarray(cmap(index)[:3], dtype=np.float32)
    rgb[masks["lifts"]] = (0.03, 0.03, 0.03)
    rgb[~valid] = (1.0, 1.0, 1.0)

    azimuth, altitude = np.deg2rad(315), np.deg2rad(40)
    slope_rad = np.deg2rad(slope)
    aspect = np.arctan2(-dzdx, dzdy)
    shade = np.sin(altitude)*np.cos(slope_rad) + np.cos(altitude)*np.sin(slope_rad)*np.cos(azimuth-aspect)
    shade = np.clip((shade + 0.3) / 1.3, 0.45, 1.0)[..., None]
    image = np.clip(rgb * shade, 0.0, 1.0)
    plt.figure(figsize=(11, 7.2))
    plt.imshow(image)
    plt.axis("off")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    if diagnostics and score is not None:
        diag = path.with_name(path.stem + "_rock_score.png")
        plt.figure(figsize=(11, 7.2))
        plt.imshow(score, cmap="magma")
        plt.colorbar(label="rock score")
        plt.axis("off")
        plt.title(title + " — rock score")
        plt.tight_layout()
        plt.savefig(diag, dpi=180, bbox_inches="tight")
        plt.close()
