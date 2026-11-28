'''
Glue per-run vorticity movies (make_run_movie.py) and SoRoLily's movies into one
grid: two columns (1x, 30x water), SoRoLily in the first row, then one row per
ALPHA_NEW_INTERPOLATOR value in increasing order, one shared colour bar on the
right. ffmpeg only re-arranges existing frames, so this takes minutes.

    python glue_movies.py OUT.mp4 RUN_DIR [RUN_DIR ...]

Each RUN_DIR needs its vorticity.mp4 from make_run_movie.py. Needs the ib2d env and ffmpeg.
'''

import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import BoundaryNorm
from matplotlib.image import imread

import make_comparison_movie as m
from make_alpha_movie import read_key
from make_run_movie import AXES, DPI, FPS, TILE, new_tile

SRL = [('SoRoLily 1×', m.HOME / 'finray_fsi/WaterLily_FSI/WaterLily_2Way_Coupling_Example/NACA0020.mp4'),
       ('SoRoLily 30×', m.SRL / 'nu30/NACA0020.mp4')]
CBAR_W = 120                 # px
RETIME = f'setpts=N/{FPS}/TB'  # frame k shown at k/FPS s, whatever the source's frame rate


def srl_crop(mp4, tmp):
    '''ffmpeg crop w:h:x:y of SoRoLily's movie to the window m.XLIM x m.YLIM.'''
    png = Path(tmp) / 'srl_probe.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '5', '-i', str(mp4), '-frames:v', '1', str(png)], check=True)
    r0, r1, c0, c1 = m.domain_box(imread(png))
    sx, sy = (c1 - c0 + 1) / m.DOMAIN[0], (r1 - r0 + 1) / m.DOMAIN[1]   # px per m
    x, y = c0 + m.XLIM[0] * sx, r0 + (m.DOMAIN[1] - m.YLIM[1]) * sy     # image rows run downwards
    w, h = (m.XLIM[1] - m.XLIM[0]) * sx, (m.YLIM[1] - m.YLIM[0]) * sy
    return f'{w:.0f}:{h:.0f}:{x:.0f}:{y:.0f}'


def colorbar_png(height, path):
    fig = plt.figure(figsize=(CBAR_W / DPI, height / DPI), dpi=DPI)
    cax = fig.add_axes([0.12, 0.05, 0.18, 0.9])
    cmap, levels = plt.get_cmap('RdBu'), np.linspace(-10, 10, 41)
    fig.colorbar(ScalarMappable(norm=BoundaryNorm(levels, cmap.N, extend='both'), cmap=cmap), cax=cax,
                 extend='both', ticks=[-10, -5, 0, 5, 10], label='vorticity [1/s]')
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def main(out, runs):
    cells = {}
    for run in runs:
        if not (run / 'vorticity.mp4').exists():
            print(f'skipping {run}: no vorticity.mp4 (run make_run_movie.py first)')
            continue
        col = 0 if read_key(run, 'MU') < 0.01 else 1
        cells[(read_key(run, 'ALPHA_NEW_INTERPOLATOR', 0.0), col)] = run / 'vorticity.mp4'
    alphas = sorted({a for a, _ in cells})
    tiles = SRL + [cells.get((a, c)) for a in alphas for c in (0, 1)]   # row by row; None = blank cell
    W, H = TILE
    l, b, w, h = AXES
    rows = len(tiles) // 2

    with tempfile.TemporaryDirectory() as tmp:
        args, chains = [], []
        def add_input(*opts):
            args.extend(opts)
            return sum(a == '-i' for a in args) - 1          # index of the input just added
        for n, tile in enumerate(tiles):
            if tile is None:
                chains.append(f'color=c=white:s={W}x{H}:r={FPS}:d={m.N_FRAMES / FPS},format=yuv420p[t{n}]')
            elif isinstance(tile, Path):
                i = add_input('-i', str(tile))
                chains.append(f'[{i}:v]{RETIME},scale={W}:{H},format=yuv420p[t{n}]')
            else:                                            # SoRoLily: its video inside an empty tile's plot area
                label, mp4 = tile
                bg = Path(tmp) / f'srl_{n}.png'
                fig, _ = new_tile(label)
                fig.savefig(bg, dpi=DPI)
                plt.close(fig)
                i_bg = add_input('-loop', '1', '-framerate', str(FPS), '-i', str(bg))
                i_v = add_input('-i', str(mp4))
                chains.append(f'[{i_v}:v]{RETIME},crop={srl_crop(mp4, tmp)},scale={w - 2}:{h - 2}[s{n}];'
                              f'[{i_bg}:v]scale={W}:{H}[b{n}];'
                              f'[b{n}][s{n}]overlay={l + 1}:{H - b - h + 1}:shortest=1,format=yuv420p[t{n}]')
        cb = Path(tmp) / 'colorbar.png'
        colorbar_png(rows * H, cb)
        i_cb = add_input('-loop', '1', '-framerate', str(FPS), '-i', str(cb))
        layout = '|'.join(f'{(n % 2) * W}_{(n // 2) * H}' for n in range(len(tiles)))
        chains.append(''.join(f'[t{n}]' for n in range(len(tiles))) + f'xstack=inputs={len(tiles)}:layout={layout}[grid]')
        chains.append(f'[{i_cb}:v]scale={CBAR_W}:{rows * H},format=yuv420p[cb];[grid][cb]hstack=inputs=2:shortest=1[out]')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *args, '-filter_complex', ';'.join(chains), '-map', '[out]',
                        '-frames:v', str(m.N_FRAMES), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(out)], check=True)
    print(f'wrote {out}: {rows} rows x 2 columns')


if __name__ == '__main__':
    main(Path(sys.argv[1]), [Path(p).resolve() for p in sys.argv[2:]])