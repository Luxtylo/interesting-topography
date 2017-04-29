#!/usr/bin/env python3
"""
Import terrain height data from OS OpenData files

Data requested from OS OpenData:
OS Terrain 50 - GB | Data type: Grid | Supply format: ASCII GRID AND GML (GRID)
From: https://www.ordnancesurvey.co.uk/opendatadownload/products.html

This provides a .zip folder, which this project expects to be unzipped into:
    "./OS - terr50_gagg_gb"

Inside that is data/ and a license
Inside data/ are a lot of folders for the Ordnance Survey national grid

In each of those folders are several zip files, which contain the data for
each of the grid squares. The important one of these is the .asc file
"""

from PIL import Image
import zipfile
import os
from shutil import rmtree
from math import floor
import numpy as np


class HeightCell:
    """
    A single cell of the height map from Ordnance Survey's site
    """
    def __init__(self, dimensions, heights, exclude=[]):
        """
        Initialise this HeightCell with the properties passed to it
        dimensions is (cols, rows, xcorner, ycorner, cellsize)
        """
        cols, rows, xcorner, ycorner, cellsize = dimensions

        self.xsize = cols
        self.ysize = rows
        self.xcorner = xcorner  # Lower left corner
        self.ycorner = ycorner  # Lower left corner
        self.size = cellsize
        self.heights = heights
        self.exclude = exclude

        valid_values = list(filter(lambda x: x is not None, self.flattened))
        self.max = max(valid_values)
        self.min = min(valid_values)


    @property
    def flattened(self):
        """
        Return a flattened list of the heights in the cell
        Yes, I'm aware of the irony in the name
        """
        flat = [item for sublist in self.heights for item in sublist]
        return [h if h not in self.exclude else None for h in flat]


def importAsc(asc_file_name):
    """
    Import a .asc file from Ordnance Survey as a HeightCell
    """

    with open(asc_file_name, "r") as asc_file:
        lines = asc_file.readlines()


    # First 5 lines are dimensions
    dimensions = (int(l.split(" ")[-1]) for l in lines[:5])

    # Lines after this are the height data
    heights = [list(map(float, l.rstrip().split(" "))) for l in lines[6:]]

    # Some values may need to be excluded
    exclude = []

    height_cell = HeightCell(dimensions, heights, exclude)

    return height_cell


def saveCellAsImage(cell, image_name):
    """
    Save a HeightCell's height data to an image
    cell should be a valid HeightCell instance
    """

    def scaleBetween(x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    # Scale point data so it goes 0-255
    # Excluded values are set to 0 (black)
    scaleTo255 = lambda x: scaleBetween(x, cell.min, cell.max, 0, 255) if x is not None else 0
    scaled_pixels = list(map(scaleTo255, cell.flattened))

    # Save image
    img = Image.new("L", (cell.xsize, cell.ysize))
    img.putdata(scaled_pixels)
    img.save(image_name)


def chooseSquare(base_dir):
    """
    Choose one of the 100x100km squares from the OS National Grid
    Prompts the user to enter the two-letter name of the chosen square
    """
    valid_square_names = sorted(os.listdir(base_dir))

    print("OS National Grid squares:")
    for a, b, c, d in zip(valid_square_names[::4], valid_square_names[1::4],
                          valid_square_names[2::4], valid_square_names[3::4]):
        print("{}, {}, {}, {}".format(a, b, c, d))

    square_name = input("Enter a square name: ").lower()

    if square_name not in valid_square_names:
        raise ValueError("Not a valid square name")

    return square_name


def extractAscsFromSquare(base_dir, tmp_dir, square_name):
    """
    Extract all .asc files from the .zip files in the chosen square
    The files are extracted into tmp_dir

    Returns list of the file names
    """
    square_base_dir = os.path.join(base_dir, square_name)

    file_names = []

    for item in os.listdir(square_base_dir):
        if not item.endswith(".zip"):
            continue    # Skip non-zip files

        item_path = os.path.join(square_base_dir, item)

        with zipfile.ZipFile(item_path, "r") as zip_ref:
            contents = zip_ref.namelist()
            asc_files = filter(lambda f: f.endswith(".asc"), contents)

            for asc_file in asc_files:
                zip_ref.extract(asc_file, tmp_dir)
                file_names.append(asc_file)

    return sorted(file_names)


if __name__ == "__main__":
    base_dir = os.path.join(".", "OS - terr50_gagg_gb", "data")
    map_data_dir = os.path.join(".", "map_data")

    square_name = chooseSquare(base_dir)
    asc_files = extractAscsFromSquare(base_dir, map_data_dir, square_name)

    # Import the cells as HeightCell objects
    height_cells = []
    cell_size = 10000           # In metres
    measurement_interval = 50   # 50m per measurement
    cell_side = cell_size / measurement_interval
    cell_res = cell_side ** 2

    for asc in asc_files:
        file_name = os.path.join(map_data_dir, asc)
        height_cells.append(importAsc(file_name))

    # Add the HeightCell info to a large grid and save an image
    # Lower left corner coords
    x_corners = [c.xcorner for c in height_cells]
    y_corners = [c.ycorner for c in height_cells]
    max_x = max(x_corners) + cell_size
    max_y = max(y_corners) + cell_size
    min_x = min(x_corners)
    min_y = min(y_corners)

    # Image dimensions
    ground_width = (max_x - min_x)
    ground_height = (max_y - min_y)
    cell_cols = ground_width // cell_size
    cell_rows = ground_width // cell_size
    img_width = int(ground_width * cell_side // cell_size)
    img_height = int(ground_height * cell_side // cell_size)

    # Use zero for default height (sea)
    #heights_combined = [0] * int(img_height * img_width)
    heights_combined = np.zeros((img_height, img_width))

    for cell in height_cells:
        # Put the cells in a grid. This creates an index starting from the
        # bottom left, going along the bottom and up row by row

        cell_col = (cell.xcorner - min_x) / cell_size
        cell_row = (cell_rows - 1) - (cell.ycorner - min_y) / cell_size
        cell_start_x = int(cell_col * cell_side)
        cell_start_y = int(cell_row * cell_side)
        #cell_idx = int(cell_row * cell_cols + cell_col)

        # The start in heights_combined for the cell
        #cell_start = int(cell_idx * cell_res)

        # Add actual height data to heights_combined
        for row, row_data in enumerate(cell.heights):
            for col, h in enumerate(row_data):
                #idx = cell_start + int(row * cell_side + col)
                #heights_combined[idx] = h
                px_col = cell_start_x + col
                px_row = cell_start_y + row
                heights_combined[px_row][px_col] = h

    def scaleBetween(x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

    # Scale point data so it goes 0-255
    # Excluded values are set to 0 (black)
    min_height = heights_combined.min()

    # Shift negative values up
    if min_height < 0:
        heights_combined -= min_height

    # Scale heights to 255
    heights_combined *= 255.0 / heights_combined.max()
    #scaleTo255 = lambda x: scaleBetween(x, min_height, max_height, 0, 255) if x is not None else 0
    #scaled_pixels = list(map(scaleTo255, heights_combined))

    # Save image
    img = Image.new("L", heights_combined.shape)
    img.putdata(heights_combined.flatten())
    img.save("test.png")

    # Import individual cell and display as image
    #file_name = os.path.join(map_data_dir, asc_files[1])
    #cell = importAsc(file_name)
    #saveCellAsImage(cell, "test.png")

    # Remove map_data_dir so files aren't included in the next iteration
    rmtree(map_data_dir)
