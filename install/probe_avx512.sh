#!/bin/bash
# Report which ICF-Free nodes have AVX-512. The install's OpenBLAS (built by
# PETSc on scotia02) uses AVX-512, so IBAMR crashes ("Illegal instruction")
# on nodes without it. Run on the head node: bash install/probe_avx512.sh
# Prints one line per node: name, avx512f count (0 = none), CPU model.

PARTITION=ICF-Free
MAX_PARALLEL=8                      # probes running at once
for node in $(sinfo -p "$PARTITION" -N -h -o "%N %t" | grep -vE 'down|drain|maint' | awk '{print $1}' | sort -u); do
    while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL" ]; do wait -n; done   # wait for a free slot
    # One tiny step per node; give up on a node that has no room within 60 s.
    srun -p "$PARTITION" --nodelist="$node" --ntasks=1 --cpus-per-task=1 --mem=100M \
         --time=00:02:00 --immediate=60 --quiet \
         bash -c 'echo "$(hostname -s) $(grep -c avx512f /proc/cpuinfo) $(lscpu | sed -n "s/^Model name: *//p")"' \
         || echo "$node UNPROBED (busy or unavailable)" &
done
wait
