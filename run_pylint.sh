#!/usr/bin/env bash
readonly REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
readonly PYLINTRC=$REPO_DIR/pylintrc

pylint --rcfile=$PYLINTRC --fail-under=9 --reports=yes ${1:-cortex}