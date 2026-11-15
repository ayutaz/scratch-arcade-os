#!/bin/bash
set -euo pipefail
printf '%s\n' 'Flash refused: this source release does not authorize firmware writes.' >&2
exit 2
