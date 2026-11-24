'''
Vorticity movie of the alpha sweep: two columns (1x, 30x water), SoRoLily in the
first row, then one row per ALPHA_NEW_INTERPOLATOR value in increasing order.
Reuses make_comparison_movie.py (readers, drawing, frame timing). A run that
stopped early keeps showing its last good frame.

    python make_alpha_movie.py OUT.mp4 RUN_DIR [RUN_DIR ...]

Each RUN_DIR is a results/<tag>_<jobid> folder. MU and ALPHA_NEW_INTERPOLATOR are
read from that run's own input2d copy (the one SET modified at submission).
'''

import re
import sys
from pathlib import Path

import numpy as np

import make_comparison_movie as m


def read_key(run, key, default=None):
    '''Top-level `key = <number>` in the run's input2d copy (comments after // ignored).'''
    for line in (run / 'input2d').read_text().splitlines():
        hit = re.match(re.escape(key) + r'\s*=\s*([-+0-9.eE]+)\s*$', line.split('//')[0])
        if hit:
            return float(hit.group(1))
    return default


def last_good_frame(run):
    '''Last frame index with a finite vorticity dump and its structure positions; None if none.'''
    steps = sorted(int(p.name.split('.')[1]) for p in (run / 'viz_IB2d').glob('visit_dump.*'))
    for step in reversed(steps):
        if step > 0 and not (run / 'hier_data_IB2d' / f'X.{step:05d}').exists():
            continue
        g = m.ibamr_omega(run, step)
        if g is not None and np.isfinite(g[2]).all():
            return step // m.STEPS_PER_FRAME
    return None


def main(out, runs):
    last, grid = {}, {}                                   # grid[(alpha, column)] = panel
    for run in runs:
        if not (run / 'input2d').exists():
            print(f'skipping {run}: no input2d (job never started?)')
            continue
        alpha = read_key(run, 'ALPHA_NEW_INTERPOLATOR', 0.0)  # missing key = run made before the new class
        col = 0 if read_key(run, 'MU') < 0.01 else 1          # 1x water: MU = 1e-3, 30x: 3e-2
        k = last[str(run)] = last_good_frame(run)
        label = f"IBAMR {['1×', '30×'][col]}, α = {alpha:g}"
        if k is None:
            label += ' (no output)'
        elif k < m.N_FRAMES - 1:
            label += f' (stopped, t = {k * m.FRAME_DT:.2f} s)'
        grid[(alpha, col)] = (label, 'ibamr', run)

    # Freeze: past its last good frame, a run keeps showing that frame.
    plain = m.ibamr_frame
    def frozen(run_dir, k, n_out):
        k_last = last[str(run_dir)]
        return None if k_last is None else plain(run_dir, min(k, k_last), n_out)
    m.ibamr_frame = frozen

    alphas = sorted({a for a, _ in grid})
    m.PANELS = [('SoRoLily 1×', 'sorolily', m.HOME / 'finray_fsi/WaterLily_FSI/WaterLily_2Way_Coupling_Example'),
                ('SoRoLily 30×', 'sorolily', m.SRL / 'nu30')]
    for a in alphas:
        m.PANELS += [grid.get((a, 0)), grid.get((a, 1))]   # None leaves the cell blank
    m.NROWS, m.NCOLS = 1 + len(alphas), 2
    m.main(out)


if __name__ == '__main__':
    main(Path(sys.argv[1]), [Path(p).resolve() for p in sys.argv[2:]])