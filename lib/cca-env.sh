# shellcheck shell=bash
# Shared CCA project config loader. Source this file, then call cca_load_env.
#
# Walks from the CWD up to / (exclusive), across nested git repos, so
# subprojects inherit the main project's config. Per directory:
#   .cca-tmux-cli  tool-specific config; sourced, then the search stops
#   .cca-env       CCA project config; sourced at EVERY level (a parent's
#                  values override a subdirectory's)
#   .env           legacy fallback; only the closest one, and only while no
#                  .cca-env/.env has been sourced yet
# Each file is sourced from its own directory, so relative paths inside it
# (.cca-env.local, ./.venv, $PWD/bin) work when called from a subdirectory.
# CCA_ENV_FILES lists the sourced files (space-separated) for diagnostics.
# Keep in sync with the loader in bin/cca-tmux-cli.

cca_source_config() {
    local start_dir="$PWD"
    cd "$1" || return
    # shellcheck source=/dev/null
    source "./$2"
    local rc=$?
    cd "$start_dir" || exit 1
    CCA_ENV_FILES="${CCA_ENV_FILES:+$CCA_ENV_FILES }$1/$2"
    return $rc
}

cca_load_env() {
    local dir env_loaded=false
    dir="$(pwd)"
    CCA_ENV_FILES=""
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/.cca-tmux-cli" ]; then
            cca_source_config "$dir" .cca-tmux-cli
            break
        fi
        if [ -f "$dir/.cca-env" ]; then
            cca_source_config "$dir" .cca-env
            env_loaded=true
        elif [ -f "$dir/.env" ] && [ "$env_loaded" = false ]; then
            cca_source_config "$dir" .env
            env_loaded=true
        fi
        dir="$(dirname "$dir")"
    done
}
