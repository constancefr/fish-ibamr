'''
Vorticity movie of one IBAMR run of the NACA0020 wing, drawn like the panels of
make_comparison_movie.py (same window, RdBu bands in +-10 1/s, white wing with a
black outline): one frame every 0.05 s, 20 fps, fixed 520 x 330 px tiles so
glue_movies.py can tile several runs. No colour bar (glue_movies.py adds one).
A run that stopped early keeps its last good frame.

    python make_run_movie.py RUN_DIR [OUT.mp4]     (default RUN_DIR/vorticity.mp4)

Needs the ib2d conda env (numpy, matplotlib, h5py) and ffmpeg.
'''

import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import make_comparison_movie as m
from make_alpha_movie import last_good_frame, read_key

TILE = (520, 330)            # px (even numbers, for the video encoder)
AXES = (50, 30, 456, 240)    # px: left, bottom, width, height; 456/240 = 0.95 m / 0.5 m, so 1 m is the same in x and y
DPI = 100
FPS = 20                     # 201 frames = 10 s, as SoRoLily's movies


def new_tile(title):
    '''Empty tile: plot area at AXES, window m.XLIM x m.YLIM, ticks and title.'''
    fig = plt.figure(figsize=(TILE[0] / DPI, TILE[1] / DPI), dpi=DPI)
    l, b, w, h = AXES
    ax = fig.add_axes([l / TILE[0], b / TILE[1], w / TILE[0], h / TILE[1]])
    ax.set_xlim(*m.XLIM); ax.set_ylim(*m.YLIM)
    ax.set_title(title, fontsize=11)
    ax.tick_params(labelsize=8)
    return fig, ax


def run_label(run):
    alpha = read_key(run, 'ALPHA_NEW_INTERPOLATOR', 0.0)   # missing key = run made before the new class
    visc = '1×' if read_key(run, 'MU') < 0.01 else '30×'
    return f'IBAMR {visc}, α = {alpha:g}'


def main(run, out):
    cmap, levels = plt.get_cmap('RdBu'), np.linspace(-10, 10, 41)
    n_out = int(np.load(m.HERE / 'wing_mesh.npz')['n_outline'])
    k_last = last_good_frame(run)
    label = run_label(run)
    if k_last is not None and k_last < m.N_FRAMES - 1:
        label += f' (stopped at {k_last * m.FRAME_DT:.2f} s)'
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(m.N_FRAMES):
            fig, ax = new_tile(f'{label}    t = {k * m.FRAME_DT:5.2f} s')
            g = None if k_last is None else m.ibamr_frame(run, min(k, k_last), n_out)
            if g is not None and np.isfinite(g[2]).all():
                m.draw_field(ax, *g, cmap, levels)
            fig.savefig(Path(tmp) / f'f_{k:04d}.png', dpi=DPI)
            plt.close(fig)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', str(Path(tmp) / 'f_%04d.png'),
                        '-vf', f'scale={TILE[0]}:{TILE[1]}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(out)],
                       check=True)
    print(f'wrote {out}: {m.N_FRAMES} frames at {FPS} fps')


if __name__ == '__main__':
    run = Path(sys.argv[1]).resolve()
    main(run, Path(sys.argv[2]) if len(sys.argv) > 2 else run / 'vorticity.mp4')