'''
Run records for IBAMR cases (adapted from fish-ib2d common/run_records.py at
9b21eda). Every run folder gets a run_info.json -- the source of truth for
that run -- and results/index.csv is generated from those files, one row per
run, every field a column. Indexes are never edited by hand: rebuild them.

The job script (e.g. cases/NACA0020/run_naca.sbatch) calls, in order:
    python3 run_records.py provenance CASE_DIR RUN_DIR             # at job start: code state
    python3 run_records.py record RUN_DIR START END EXIT_CODE      # at job end (epoch seconds)
    python3 run_records.py index RESULTS_DIR [...]                 # rebuild index.csv
`index` also fills in peak memory from sacct for jobs that have finished.
Standard library only.
'''

import csv
import glob
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MAX_UNTRACKED_BYTES = 200_000  # untracked files larger than this are listed, not copied into code.diff


def read_input2d(path):
    '''Every top-level `NAME = value` of an IBAMR input file (blocks skipped):
    numbers as int/float, quoted strings unquoted, expressions as raw text.'''
    values, depth = {}, 0
    for line in Path(path).read_text().splitlines():
        line = line.split('//')[0].strip()
        if depth == 0 and (m := re.match(r'([A-Za-z_]\w*)\s*=\s*(.+)$', line)):
            raw = m.group(2).strip()
            for cast in (int, float):
                try:
                    values[m.group(1)] = cast(raw)
                    break
                except ValueError:
                    pass
            else:
                values[m.group(1)] = raw.strip('"')
        depth += line.count('{') - line.count('}')
    return values


def _git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True).stdout


def git_provenance(case_dir, diff_path):
    '''
    Commit, branch, uncommitted changes, submodule commits. Uncommitted
    changes (tracked diffs, plus small untracked files) are saved to diff_path;
    .gitignore keeps generated files out of both.
    '''
    status = _git('status', '--porcelain', cwd=case_dir).splitlines()
    if status:
        root = Path(_git('rev-parse', '--show-toplevel', cwd=case_dir).strip())
        diff = _git('diff', 'HEAD', cwd=root)
        for f in _git('ls-files', '--others', '--exclude-standard', cwd=root).splitlines():
            if (root / f).stat().st_size <= MAX_UNTRACKED_BYTES:
                diff += _git('diff', '--no-index', '/dev/null', f, cwd=root)
        Path(diff_path).write_text(diff)
    return dict(
        commit=_git('rev-parse', 'HEAD', cwd=case_dir).strip(),
        branch=_git('rev-parse', '--abbrev-ref', 'HEAD', cwd=case_dir).strip(),
        uncommitted_changes=bool(status),
        changed_files=[s.strip() for s in status],
        diff_file=Path(diff_path).name if status else None,
        submodules=_git('submodule', 'status', cwd=case_dir).strip(),
    )


def provenance(case_dir, run_dir):
    '''The code a run uses, saved into run_dir at job start (so later edits
    to the repo can't change it): git state, IBAMR install, MPI version.'''
    run_dir = Path(run_dir)
    info = dict(
        **git_provenance(case_dir, run_dir / 'code.diff'),
        ibamr=[Path(p).name for p in sorted(glob.glob(str(Path.home() / 'autoibamr/packages/IBAMR-*')))],
        mpi=subprocess.run(['mpirun', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
    )
    (run_dir / 'provenance.json').write_text(json.dumps(info, indent=2) + '\n')


def _cpu_model():
    for line in Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith('model name'):
            return line.split(':', 1)[1].strip()


def outcome(run_dir, end_time, exit_code):
    '''How far the run got, from the last "simulation time is" in its log.'''
    log = '\n'.join(Path(f).read_text() for f in glob.glob(str(Path(run_dir) / '*.log')))
    times = [float(t) for t in re.findall(r'simulation time is\s+([-+0-9.eE]+)', log)]
    last = times[-1] if times else None
    if last is not None and last >= end_time * (1 - 1e-9):
        status = 'completed'
    else:
        status = 'failed' if exit_code != 0 else 'incomplete'
    return dict(status=status, last_time=last, exit_code=exit_code,
                nan_in_log=bool(re.search(r'\bnan\b', log, re.IGNORECASE)))


def record(run_dir, start, end, exit_code):
    '''Writes run_dir/run_info.json from the run folder's own files.'''
    run_dir = Path(run_dir)
    inputs = read_input2d(run_dir / 'input2d')
    out = outcome(run_dir, inputs['END_TIME'], exit_code)
    steps = round(out['last_time'] / inputs['DT']) if out['last_time'] else 0
    wall = end - start
    sizes = [f.stat().st_size for f in run_dir.rglob('*') if f.is_file()]

    def load(name):
        p = run_dir / name
        return json.loads(p.read_text()) if p.exists() else None

    info = dict(
        run=dict(name=run_dir.name, tag=os.environ.get('TAG'), set=os.environ.get('SET'),
                 job_id=os.environ.get('SLURM_JOB_ID'),
                 node=platform.node(), cpu=_cpu_model(), mpi_processes=int(os.environ.get('SLURM_NTASKS', 1))),
        inputs=dict(input2d=inputs, case_params=load('case_params.json')),
        mesh=load('mesh_info.json'),
        timing=dict(start=datetime.fromtimestamp(start).isoformat(timespec='seconds'),
                    end=datetime.fromtimestamp(end).isoformat(timespec='seconds'),
                    wall_s=wall, steps=steps, ms_per_step=round(1000 * wall / steps, 2) if steps else None),
        outcome=out,
        provenance=load('provenance.json'),
        outputs=dict(n_snapshots=len(list(run_dir.glob('*/visit_dump.*'))),
                     size_mb=round(sum(sizes) / 1e6, 1)),
        memory=dict(max_rss_mb=None),
    )
    write_run_info(run_dir, info)


def _sacct_max_rss_mb(job_id):
    '''Peak memory of a finished job over all its steps, or None (still running / unknown).'''
    out = subprocess.run(['sacct', '-j', str(job_id), '-n', '-P', '--format=State,MaxRSS'],
                         capture_output=True, text=True).stdout.split()
    if not out or any(s.startswith(('RUNNING', 'PENDING')) for s in out):
        return None
    scale = dict(K=1e-3, M=1, G=1e3)
    rss = [float(m.group(1)) * scale[m.group(2)] for s in out if (m := re.search(r'([0-9.]+)([KMG])$', s))]
    return round(max(rss), 1) if rss else None


def write_run_info(run_dir, info):
    (Path(run_dir) / 'run_info.json').write_text(json.dumps(info, indent=2) + '\n')


def _flatten(d, prefix=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f'{prefix}{k}.'))
        elif isinstance(v, list):
            out[f'{prefix}{k}'] = '; '.join(map(str, v))
        else:
            out[f'{prefix}{k}'] = v
    return out


def write_index(results_dir):
    '''
    results_dir/index.csv: one row per run_info.json at any depth below
    results_dir, every field a column, plus `folder` (the run's path relative
    to results_dir). Fills in memory.max_rss_mb from sacct where missing.
    '''
    results_dir = Path(results_dir)
    rows = []
    for root, dirs, files in os.walk(results_dir):
        if 'run_info.json' in files:
            dirs.clear()  # a run folder: don't descend into its output
            info = json.loads((Path(root) / 'run_info.json').read_text())
            if info['memory']['max_rss_mb'] is None and info['run']['job_id']:
                info['memory']['max_rss_mb'] = _sacct_max_rss_mb(info['run']['job_id'])
                write_run_info(root, info)
            rows.append({'folder': str(Path(root).relative_to(results_dir)), **_flatten(info)})
    rows.sort(key=lambda r: str(r.get('timing.start') or ''))
    path = results_dir / 'index.csv'
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == '__main__':
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 2 else (None, [])
    if cmd == 'provenance' and len(args) == 2:
        provenance(*args)
    elif cmd == 'record' and len(args) == 4:
        record(args[0], int(args[1]), int(args[2]), int(args[3]))
    elif cmd == 'index':
        for p in args:
            print('wrote', write_index(p))
    else:
        sys.exit(__doc__)
