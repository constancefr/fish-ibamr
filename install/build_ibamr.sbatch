#!/bin/bash
# 1. Build IBAMR and its dependencies into ~/autoibamr with autoibamr (external/autoibamr).
# Submit from the head node: sbatch install/build_ibamr.sbatch
#SBATCH --job-name=build-ibamr
#SBATCH --partition=ICF-Free        # research partition (the default, Teaching, is for students)
#SBATCH --cpus-per-task=8           # compile 8 files in parallel
#SBATCH --mem=16G                   # compiling PETSc/libMesh needs a few GB per process
#SBATCH --time=06:00:00             # generous; we'll check the real time with sacct afterwards
#SBATCH --output=%x_%j.out          # log: build-ibamr_<jobid>.out, in the folder you submit from
set -euo pipefail                   # stop at the first failing command

# 2. Build on the node's local disk
# autoibamr builds inside <prefix>/tmp (thousands of small files, slow on the
# shared filesystem), so point that folder at this node's local disk.
PREFIX="$HOME/autoibamr"
SCRATCH="/disk/scratch/$USER/autoibamr-build-$SLURM_JOB_ID"
mkdir -p "$PREFIX" "$SCRATCH"
ln -sfn "$SCRATCH" "$PREFIX/tmp"    # create symlink
trap 'rm -rf "$SCRATCH" "$PREFIX/tmp"' EXIT   # clean up when the job ends, even on failure

# 3. Run autoibamr
# Slurm runs a copy of this script, so locate the repo from where it was submitted.
AUTOIBAMR="$SLURM_SUBMIT_DIR/external/autoibamr/autoibamr.sh"
[ -x "$AUTOIBAMR" ] || { echo "Submit from the fish-ibamr root (not found: $AUTOIBAMR)"; exit 1; }
"$AUTOIBAMR" --prefix="$PREFIX" --jobs="$SLURM_CPUS_PER_TASK" --yes


