# Beam Analyzer

A desktop application for beam cross-section analysis from STEP (CAD) files.

## Features

1. **STEP Import & Slicing**: Load a STEP file and slice it into cross-sections along the X axis. The number and position of sections can be adjusted numerically or by dragging station lines on the side view.

2. **Section Properties**: For each cross-section, computes:
   - Area
   - Centroid (Yc, Zc)
   - Second moments of inertia (Iyy, Izz, Iyz)
   - Principal moments (I1, I2) and angle
   - Extreme coordinates relative to centroid (Y_max, Y_min, Z_max, Z_min)

3. **Shear Stress** (Shear tab): Define supports and applied loads (point loads,
   distributed loads, point moments) on a determinate beam. The app builds the
   shear-force V(x) and bending-moment M(x) diagrams, then computes the transverse
   shear-stress distribution `tau(z) = V*Q / (Iyy*t)` through the depth of each
   cross-section. Plots the full `tau(z)` profile per station and exports it to CSV.

4. **Visualization & Export**:
   - Side view plot with draggable station lines
   - 2D cross-section view at each station
   - Properties plotted against X station
   - Export all properties to CSV

## Installation

### Option 1: Install from source (requires Python 3.10+)

```bash
pip install .
beam-analyzer
```

### Option 2: Standalone executable (no Python required)

```bash
pip install -e ".[dev]"
python build_exe.py
```

The executable will be in `dist/BeamAnalyzer/BeamAnalyzer.exe`.

## Usage

1. **Open a STEP file**: Click "Open STEP..." and select your `.step` or `.stp` file.
2. **Generate side view image** (optional): Click "Generate Side View Image" to create a wireframe
   projection of the STEP geometry. This image is automatically overlaid on the side view plot with
   matching scale and position. Toggle visibility with the checkbox.
3. **Set slice parameters**: Adjust the number of stations and X range.
4. **Process**: Click "Process STEP" to compute cross-sections.
5. **Adjust stations**: Drag vertical lines on the side view to reposition stations, then click
   "Re-slice at current positions".
6. **View results**: Switch to the "Results" tab to see properties plotted and export to CSV.

## Dependencies

- numpy >= 1.24
- shapely >= 2.0
- pandas >= 2.0
- matplotlib >= 3.7
- cadquery-ocp >= 7.7 (OpenCASCADE Python bindings)
- PySide6 >= 6.6 (Qt6 desktop UI)

## Project Structure

```
beam_analyzer/
├── main.py                  # Entry point
├── core/
│   ├── step_slicer.py       # STEP parsing and plane slicing
│   ├── section_props.py     # Geometric properties (Green's formulas)
│   ├── beam_statics.py      # Determinate beam solver -> V(x), M(x)
│   └── shear_stress.py      # Transverse shear stress tau = V*Q/(I*t)
└── ui/
    ├── main_window.py       # Main application window
    ├── state.py             # Shared application state
    ├── plot_widget.py       # Matplotlib canvas wrapper
    ├── worker.py            # Background thread workers
    └── tabs/
        ├── tab_geometry.py  # STEP load, slice, plots
        ├── tab_results.py   # Properties table, CSV export, plots
        └── tab_shear.py     # Loads, V/M diagrams, shear-stress tau(z)
```
