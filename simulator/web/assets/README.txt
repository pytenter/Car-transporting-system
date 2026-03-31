Place the fixed Guangzhou Panyu assets here:

- panyu-basemap.png
- panyu-roadmask.png (optional but recommended)
- main_roads_black_white_cropped.png (also accepted)

The frontend loads the basemap from:

/assets/panyu-basemap.png

The backend can build a local road-network scenario from:

- panyu-roadmask.png when present
- main_roads_black_white_cropped.png when present
- otherwise it falls back to extracting major roads from panyu-basemap.png
