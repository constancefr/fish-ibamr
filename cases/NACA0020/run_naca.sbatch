#!/bin/bash
# Run the NACA0020 case on node scratch, copy the run folder to results/<tag>_<jobid>
# (also after a failure or timeout), write its run record, rebuild results/index.csv,
# then render the vorticity movie.
# Batch:       sbatch --job-name=<tag> run_naca.sbatch      (from this folder, after building)
# Interactive: TAG=<tag> bash run_naca.sbatch                (inside an srun session with --ntasks)
# Optional SET="KEY=VALUE ..." overrides top-level input2d values in this run's copy only,
# e.g. SET="MU=0.030069" sbatch --job-name=mu30x_cui run_naca.sbatch
#SBATCH --job-name=naca-ibamr
#SBATCH --partition=ICF-Free
#SBATCH --exclude=landonia[03,05,08,11,21,23,25],crannog03,damnii10   # no AVX-512 (install/probe_avx512.sh)
#SBATCH --ntasks=4
#SBATCH --mem=4G
#SBATCH --time=24:00:00             # generous: first full run; check Elapsed with sacct afterwards
#SBATCH --signal=B:TERM@300         # warn the script 5 min before the time limit, to copy back
#SBATCH --output=%x_%j.out
set -euo pipefail

CASE="$HOME/finray_fsi/fish-ibamr/cases/NACA0020"
RECORDS="$HOME/finray_fsi/fish-ibamr/common/run_records.py"
export TAG="${TAG:-$SLURM_JOB_NAME}"
NAME="${TAG}_${SLURM_JOB_ID}"
RUN="/disk/scratch/$USER/$NAME"
DEST="$CASE/results/$NAME"
export TMPDIR="/disk/scratch/$USER/tmp_$NAME"   # node /tmp can be full: mpirun, VisIt, Python temp files go here
START=$(date +%s)
RC=0

finish() {
    local end=$(date +%s)
    cd /
    # movie first, from node scratch (fast local reads); skipped at the time limit so the copy-back gets the time
    if [ "$RC" -ne 143 ]; then
        bash -c 'source /opt/conda/etc/profile.d/conda.sh && conda activate ib2d && MPLBACKEND=Agg python "$0" "$1"' \
            "$CASE/make_run_movie.py" "$RUN" || echo "movie failed"
    fi
    mkdir -p "$CASE/results" && cp -r "$RUN" "$DEST" && rm -rf "$RUN"
    python3 "$RECORDS" record "$DEST" "$START" "$end" "$RC" || echo "run record failed"
    python3 "$RECORDS" index "$CASE/results" || echo "index failed"
    rm -rf "$TMPDIR"
}
trap finish EXIT

mkdir -p "$RUN" "$TMPDIR" && cd "$RUN"
cp "$CASE"/{input2d,wing.vertex,wing.spring,wing.target,case_params.json,mesh_info.json} .
for kv in ${SET:-}; do
    key="${kv%%=*}"
    grep -q "^${key}\s*=" input2d || { echo "SET: no top-level $key in input2d"; RC=1; exit 1; }
    sed -i "s|^${key}\s*=.*|${key} = ${kv#*=}   // SET at submission|" input2d
done
python3 "$RECORDS" provenance "$CASE" "$RUN"
mpirun -np "$SLURM_NTASKS" "$CASE/build/main2d" input2d &
trap 'kill $! 2>/dev/null; wait $! || true; RC=143; exit 143' TERM
wait $! || RC=$?
exit $RC
