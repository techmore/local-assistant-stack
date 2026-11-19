# SPDX-License-Identifier: MIT
# Source this to get the isolated Hermes environment for the lab.
# Everything Hermes reads or writes is redirected inside the lab directory.
export LAB="${LAB:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)}"
export HERMES_HOME="$LAB/hermes-home"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
export UV_CACHE_DIR="$LAB/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$LAB/.uv-python"
export HF_HOME="$LAB/.hf"
