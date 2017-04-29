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
    heights = [list(map(float, l.rstrip().split(" "))) for l in lines[5:]]

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

    square_name = input("Enter a square name, or multiple space-separated:\n")

    square_names = square_name.lower().split(" ")

    for name in square_names:
        if name not in valid_square_names:
            raise ValueError("\"{}\" not a valid square name".format(name))

    return square_names


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


def extractCellDataFromAscs(map_data_dir, asc_list):
    """
    Return HeightCell instances for all .asc files in asc_list
    The asc files should be in map_data_dir already
    """

    return [importAsc(os.path.join(map_data_dir, a)) for a in asc_list]


def getDimensions(height_cells):
    """
    Get dimensions needed for scaling
    Return dict:
        cell_size   = Cell size in metres
        cell_side   = Number of measurements (pixels) along one side of a cell
        cell_rows   = Number of rows of cells in the image
        img_width   = Width in pixels of the output image
        img_height  = Height in pixels of the output image
        min_x       = Minimum x coordinate (metres)
        min_y       = Minimum y coordinate (metres)
    """
    # Setup image grid parameters
    cell_size = 10000           # In metres
    measurement_interval = 50   # 50m per measurement
    cell_side = cell_size / measurement_interval
    cell_res = cell_side ** 2

    # Get image dimensions from real-life size
    x_corners = [c.xcorner for c in height_cells]
    y_corners = [c.ycorner for c in height_cells]
    max_x = max(x_corners) + cell_size
    max_y = max(y_corners) + cell_size
    min_x = min(x_corners)
    min_y = min(y_corners)

    ground_width = (max_x - min_x)
    ground_height = (max_y - min_y)
    cell_cols = ground_width // cell_size
    cell_rows = ground_width // cell_size
    img_width = int(ground_width * cell_side // cell_size)
    img_height = int(ground_height * cell_side // cell_size)

    return {"cell_size": cell_size,
            "cell_side": cell_side,
            "cell_rows": cell_rows,
            "img_width": img_width,
            "img_height": img_height,
            "min_x": min_x,
            "min_y": min_y,
            "max_y": max_y}


def scaleHeightData(heights):
    """
    Scale height data from its current range to 0-255 for image output
    """

    min_height = heights.min()

    # Shift any negative values up
    if min_height < 0:
        heights -= min_height

    # Scale heights to 255
    heights *= 255.0 / heights.max()
    return heights


def combineCells(height_cells):
    """
    Combine all height cells into one array and return it
    """

    dims = getDimensions(height_cells)

    # Use zero for default height (sea)
    heights_combined = np.zeros((dims["img_height"], dims["img_width"]))

    for cell in height_cells:
        # Get the start x and y indices of the cell
        cell_col = (cell.xcorner - dims["min_x"]) / dims["cell_size"]
        cell_row = (dims["max_y"] - cell.ycorner) / dims["cell_size"] - 1
        cell_start_x = int(cell_col * dims["cell_side"])
        cell_start_y = int(cell_row * dims["cell_side"])

        # Add actual height data to heights_combined
        for row, row_data in enumerate(cell.heights):
            for col, h in enumerate(row_data):
                # Get the pixel locations of this pixel
                px_col = cell_start_x + col
                px_row = cell_start_y + row

                heights_combined[px_row][px_col] = h

    return heights_combined


def makeImage(base_dir, map_data_dir, image_name, square_names):
    """
    Generate an image from the chosen square
    """

    asc_files = []
    for square in square_names:
        asc_files.extend(extractAscsFromSquare(base_dir, map_data_dir, square))

    # Import the cells as HeightCell objects
    height_cells = extractCellDataFromAscs(map_data_dir, asc_files)

    # Merge all HeightCells into one array
    heights = combineCells(height_cells)

    # Scale to 0-255
    heights = scaleHeightData(heights)

    # Ensure extension on image name
    if not image_name.endswith(".png"):
        image_name += ".png"

    # Save image
    img = Image.new("L", heights.shape)
    img.putdata(heights.flatten())
    img.save(image_name)

    # Remove map_data_dir so files aren't included in the next iteration
    rmtree(map_data_dir)


def interactiveMakeImage(base_dir, map_data_dir, image_name):
    """
    Interactively select grid squares and generate an image
    """

    square_names = chooseSquare(base_dir)

    image_name_new = input(
            "Image name (default=\"{}\"): ".format(image_name))

    if image_name_new != "":
        image_name = image_name_new

    makeImage(base_dir, map_data_dir, image_name, square_names)


if __name__ == "__main__":
    base_dir = os.path.join(".", "OS - terr50_gagg_gb", "data")
    map_data_dir = os.path.join(".", "map_data")
    image_name = "image"
    
    interactiveMakeImage(base_dir, map_data_dir, image_name)
