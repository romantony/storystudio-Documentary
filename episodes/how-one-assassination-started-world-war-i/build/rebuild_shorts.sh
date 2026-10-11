#!/bin/bash
cd "$(dirname "$0")/.."
for s in a_spark b_myth c_matters; do python3 build/gen_short.py $s build && bash shorts/$s/build/assemble.sh; done
echo ALLDONE
