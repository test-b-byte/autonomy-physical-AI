#!/bin/bash
# Build and run the C2 operations picture. Usage: ./run.sh   or   ./run.sh --no-sim
cd "$(dirname "$0")"
rm -rf build && javac -d build $(find src -name "*.java") && java -Xmx2g -cp build c2.app.Main --assets=assets "$@"
