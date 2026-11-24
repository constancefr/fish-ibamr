#!/bin/bash
# Alpha sweep of the NACA0020 case (CUI, 1x and 30x water): one run_naca.sbatch job per
# (viscosity, alpha), then one movie job that starts once all of them have ended
# (afterany: also after a failure or timeout, so blown-up runs still get a panel).
# Run on the head node, after building:   bash submit_alpha_sweep.sh
set -euo pipefail
cd "$(dirname "$0")"

ALPHAS="0.0 0.01 0.02 0.03 0.04 0.05"             # ALPHA_NEW_INTERPOLATOR [1/(Pa s)]; explicit limit ~0.05
declare -A MU=([mu1x]=0.001 [mu30x]=0.030069)    # same values as the CUI baselines (index.csv)

ids=(); dirs=()
for v in mu1x mu30x; do
    for a in $ALPHAS; do
        tag="${v}_cui_a${a}"
        id=$(SET="MU=${MU[$v]} ALPHA_NEW_INTERPOLATOR=$a" \
             sbatch --parsable --job-name="$tag" --time=02:00:00 run_naca.sbatch)
        id="${id%%;*}"                            # --parsable may append ";cluster"
        ids+=("$id"); dirs+=("results/${tag}_${id}")
        echo "submitted $tag as job $id"
    done
done

deps=$(IFS=:; echo "${ids[*]}")
mid=$(sbatch --parsable --dependency="afterany:$deps" --job-name=alpha_movie \
      --partition=ICF-Free --ntasks=1 --mem=4G --time=02:00:00 --output=alpha_movie_%j.out \
      --wrap="source /opt/conda/etc/profile.d/conda.sh && conda activate ib2d && \
MPLBACKEND=Agg python make_alpha_movie.py results/alpha_sweep_cui.mp4 ${dirs[*]}")
echo "movie job ${mid%%;*} waits for jobs $deps"