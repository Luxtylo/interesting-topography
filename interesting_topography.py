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
import os


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
        self.xcorner = xcorner
        self.ycorner = ycorner
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

    # Some values need to be excluded
    exclude = [-0.9]

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


if __name__ == "__main__":
    base_dirname = "./OS - terr50_gagg_gb/data"
    # Allow user to choose a square from the national grid
    valid_square_names = sorted(os.listdir(base_dirname))

    print("OS National Grid squares:")
    for a, b, c, d in zip(valid_square_names[::4], valid_square_names[1::4],
                          valid_square_names[2::4], valid_square_names[3::4]):
        print("{}, {}, {}, {}".format(a, b, c, d))

    square_name = input("Enter a square name: ").lower()

    if square_name not in valid_square_names:
        raise ValueError("Not a valid square name")

    # Unzip all of that square's data (cells) into a temp folder
    # Import the cells as HeightCell objects
    # Add the HeightCell info to a large grid and save an image

    # Import individual cell and display as image
    #file_name = "OS - terr50_gagg_gb/data/hp/hp40_OST50GRID_20160726/HP40.asc"
    #cell = importAsc(file_name)
    #saveCellAsImage(cell, "test.png")
