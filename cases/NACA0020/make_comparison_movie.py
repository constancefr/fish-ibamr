'''
2 x 4 vorticity movie: SoRoLily, IB2d and IBAMR runs of the NACA0020 wing,
frame by frame at the same instants (every code saves a frame every 0.05 s
from t = 0), same zoom, same colour scale (+-10 1/s, RdBu), one shared colour
bar. Panels are listed in PANELS below; None leaves a cell blank.

    python make_comparison_movie.py [OUT.mp4]      (default results/comparison_2x4.mp4)

Needs the ib2d conda env (numpy, matplotlib, h5py, vtk) and ffmpeg. SoRoLily
and IB2d panels reuse fish-ib2d cases/NACA0020_Wing/make_comparison_movie.py
(9b21eda): SoRoLily's own movie frames cropped to its plotted domain; IB2d's
Omega.*.vtk with the wing outline from wing_history.npz.
'''

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import wing_case

HERE = Path(__file__).resolve().parent
HOME = Path.home()
SRL = HOME / 'finray_fsi/sim_data/fish-ib2d/NACA0020_Wing/sorolily_matched_re'
IB2D = HOME / 'finray_fsi/sim_data/fish-ib2d/NACA0020_Wing/stage4_ladder/results'
RES = HERE / 'results'

PANELS = [  # (label, kind, folder), row by row
    ('SoRoLily 1×', 'sorolily', HOME / 'finray_fsi/WaterLily_FSI/WaterLily_2Way_Coupling_Example'),
    ('SoRoLily 30×', 'sorolily', SRL / 'nu30'),
    # ('IBAMR CENTERED 1×', 'ibamr', RES / 'mu1x_centered_3708249'),
    # ('IBAMR CENTERED 30×', 'ibamr', RES / 'mu30x_centered_3708201'),
    ('IBAMR CUI 1×', 'ibamr', RES / 'mu1x_cui_3710112'),
    ('IBAMR CUI 30×', 'ibamr', RES / 'mu30x_cui_3710111'),
    None,
    ('IB2d 30×', 'ib2d', IB2D / 'Nx192_mu30w_20261018-200841'),
]
NROWS, NCOLS = 3, 2
FRAME_DT, N_FRAMES, STEPS_PER_FRAME = 0.05, 201, 250   # IBAMR: VIZ_INTERVAL = 250 steps of 2e-4 s
DOMAIN = (1.2, 1.2)                                    # m, all three codes
XLIM, YLIM = (0.25, 1.2), (0.35, 0.85)                 # m: the wing and its near wake


# --- SoRoLily: its own movie frames, cropped to the plotted domain ----------

def soro_frames(case_dir, tmp, tag):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(Path(case_dir) / 'NACA0020.mp4'),
                    str(Path(tmp) / f'{tag}_%04d.png')], check=True)
    return sorted(Path(tmp).glob(f'{tag}_*.png'))


def domain_box(img):
    '''Pixel box of SoRoLily's plotted domain: the non-white area left of the colour bar.'''
    rgb = img[..., :3]
    if rgb.max() > 1.5:
        rgb = rgb / 255.0
    w = rgb.shape[1]
    non_white = np.any(rgb[:, : int(0.8 * w)] < 0.985, axis=2)
    rows, cols = np.where(non_white)
    return rows.min(), rows.max(), cols.min(), cols.max()


# --- IB2d: Omega.*.vtk on its uniform grid, outline from wing_history.npz ----

def read_scalar_vtk(path):
    import vtk
    from vtk.util import numpy_support as ns
    r = vtk.vtkStructuredPointsReader()
    r.SetFileName(str(path))
    r.Update()
    nx, ny, _ = r.GetOutput().GetDimensions()
    return ns.vtk_to_numpy(r.GetOutput().GetPointData().GetScalars()).reshape(ny, nx)


def ib2d_frame(run_dir, k, hist, n_out):
    f = Path(run_dir) / 'viz_IB2d' / f'Omega.{k:04d}.vtk'
    if not f.exists():
        return None
    w = read_scalar_vtk(f)
    ny, nx = w.shape
    i = int(np.argmin(np.abs(hist['t'] - k * FRAME_DT)))
    return np.arange(nx) * DOMAIN[0] / nx, np.arange(ny) * DOMAIN[1] / ny, w, hist['pos'][i, :n_out].astype(float)


# --- IBAMR: Omega from the SAMRAI viz dump, outline from hier_data X.* -------

def ibamr_omega(run_dir, step):
    '''Node-centred Omega on the whole grid, assembled from every patch of
    viz_IB2d/visit_dump.<step> (summary.samrai gives each patch's index box).'''
    import h5py
    d = Path(run_dir) / 'viz_IB2d' / f'visit_dump.{step:05d}'
    if not d.exists():
        return None
    with h5py.File(d / 'summary.samrai', 'r') as s:
        ext, pmap = s['extents/patch_extents'][:], s['extents/patch_map'][:]
        dx = s['BASIC_INFO/dx'][0][:2]
    n = ext['upper'][:, :2].max(axis=0) + 2              # nodes per direction
    w = np.full((n[1], n[0]), np.nan)
    for e, m in zip(ext, pmap):
        (i0, j0), (i1, j1) = e['lower'][:2], e['upper'][:2] + 1
        with h5py.File(d / f"processor_cluster.{m['file_cluster_number']:05d}.samrai", 'r') as f:
            a = f[f"processor.{m['processor_number']:05d}/level.{m['level_number']:05d}"
                  f"/patch.{m['patch_number']:05d}/Omega"][:]
        w[j0:j1 + 1, i0:i1 + 1] = a.reshape(j1 - j0 + 1, i1 - i0 + 1)   # x fastest
    return np.arange(n[0]) * dx[0], np.arange(n[1]) * dx[1], w


def ibamr_outline(run_dir, step, n_out):
    if step == 0:
        return np.loadtxt(Path(run_dir) / 'wing.vertex', skiprows=1, max_rows=n_out)
    text = (Path(run_dir) / 'hier_data_IB2d' / f'X.{step:05d}').read_text()
    vals = [float(v) for v in text.splitlines()          # PETSc VecView: one value per line, plus headers
            if re.fullmatch(r'\s*[-+]?[0-9.]+(e[-+]?[0-9]+)?\s*', v, re.I)]
    return np.array(vals).reshape(-1, 2)[:n_out]


def ibamr_frame(run_dir, k, n_out):
    g = ibamr_omega(run_dir, k * STEPS_PER_FRAME)
    return None if g is None else (*g, ibamr_outline(run_dir, k * STEPS_PER_FRAME, n_out))


# --- drawing -----------------------------------------------------------------

def draw_field(ax, xs, ys, w, outline, cmap, levels):
    cf = ax.contourf(xs, ys, np.clip(w, -10, 10), levels=levels, cmap=cmap, extend='both')
    o = np.vstack([outline, outline[:1]])
    ax.fill(o[:, 0], o[:, 1], color='white', zorder=3)
    ax.plot(o[:, 0], o[:, 1], 'k-', lw=1.0, zorder=4)
    return cf


def main(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.image import imread

    cmap, levels = plt.get_cmap('RdBu'), np.linspace(-10, 10, 41)
    flow = wing_case.load_case_params()['flow']
    n_out_ibamr = int(np.load(HERE / 'wing_mesh.npz')['n_outline'])
    with tempfile.TemporaryDirectory() as tmp:
        src = {}
        print('extracting SoRoLily frames ...', flush=True)
        for p, panel in enumerate(PANELS):
            if panel is None:
                continue
            _, kind, folder = panel
            if kind == 'sorolily':
                frames = soro_frames(folder, tmp, f'soro{p}')
                src[p] = (frames, domain_box(imread(frames[len(frames) // 2])))
            elif kind == 'ib2d':
                src[p] = (np.load(folder / 'viz_IB2d' / 'wing_history.npz'),
                          int(np.load(folder / 'wing_mesh.npz')['n_outline']))
        for k in range(N_FRAMES):
            fig, axs = plt.subplots(NROWS, NCOLS, figsize=(5.2 * NCOLS, 3.3 * NROWS))
            cf = None
            for p, ax in enumerate(axs.flat):
                if PANELS[p] is None:
                    ax.axis('off')
                    continue
                label, kind, folder = PANELS[p]
                if kind == 'sorolily':
                    frames, (r0, r1, c0, c1) = src[p]
                    if k < len(frames):
                        ax.imshow(imread(frames[k])[r0:r1 + 1, c0:c1 + 1], extent=(0, DOMAIN[0], 0, DOMAIN[1]))
                else:
                    g = ib2d_frame(folder, k, *src[p]) if kind == 'ib2d' else ibamr_frame(folder, k, n_out_ibamr)
                    if g is not None and np.isfinite(g[2]).all():
                        cf = draw_field(ax, *g, cmap, levels)
                ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.set_aspect('equal')
                ax.set_title(label, fontsize=11)
                ax.tick_params(labelsize=8)
            if cf is not None:
                fig.colorbar(cf, ax=axs, shrink=0.8, label='vorticity [1/s]', ticks=[-10, -5, 0, 5, 10])
            t = k * FRAME_DT
            fig.suptitle(f't = {t:5.2f} s     angle of attack {np.degrees(wing_case.aoa_rad(t, flow)):4.1f}°',
                         fontsize=13)
            fig.savefig(Path(tmp) / f'cmp_{k:04d}.png', dpi=80)
            plt.close(fig)
            if k % 20 == 0:
                print(f'frame {k}/{N_FRAMES - 1}', flush=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '20', '-i', str(Path(tmp) / 'cmp_%04d.png'),
                        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        str(out)], check=True)
    print(f'wrote {out}: {N_FRAMES} frames')


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RES / 'comparison_3x2.mp4')
