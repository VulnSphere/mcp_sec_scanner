#!/usr/bin/env bash
set -euo pipefail

show_usage() {
  echo "Usage: $0 -i <ip_range> -p <ports>"
  exit 1
}

check_install_masscan() {
  if command -v masscan >/dev/null 2>&1; then
    echo "masscan is already installed"
    return
  fi
  echo "masscan not found. Installing..."
  os=$(uname)
  if [[ "$os" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      brew install masscan
    else
      echo "Homebrew not found. Please install Homebrew: https://brew.sh/" >&2
      exit 1
    fi
  elif [[ "$os" == "Linux" ]]; then
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      case "$ID" in
        ubuntu|debian)
          sudo apt-get update && sudo apt-get install -y masscan ;;
        centos|rhel|fedora)
          sudo yum install -y epel-release && sudo yum install -y masscan ;;
        arch)
          sudo pacman -Sy --noconfirm masscan ;;
        *)
          echo "Unsupported Linux distro: $ID" >&2
          exit 1 ;;
      esac
    else
      echo "/etc/os-release not found. Cannot install masscan." >&2
      exit 1
    fi
  else
    echo "Unsupported OS: $os" >&2
    exit 1
  fi
}

parse_args() {
  if [[ $# -eq 0 ]]; then
    show_usage
  fi
  while getopts "i:p:h" opt; do
    case "$opt" in
      i) IP_RANGE=$OPTARG ;;
      p) PORTS=$OPTARG ;;
      h) show_usage ;;
      *) show_usage ;;
    esac
  done
  if [[ -z "${IP_RANGE:-}" || -z "${PORTS:-}" ]]; then
    show_usage
  fi
}

main() {
  parse_args "$@"
  check_install_masscan
  echo "Scanning $IP_RANGE on ports $PORTS..."
  masscan -p "$PORTS" "$IP_RANGE" -oJ ips.json
  jq -r '.[].ip' ips.json | xargs -P5 -I{} sh -c '
    ip="{}"
    if curl -sS --max-time 2 "http://${ip}:${PORTS}/sse" 2>/dev/null | grep -q "event: endpoint"; then
      echo "!!!$ip contains event: endpoint"
    fi
  '
}

main "$@"
