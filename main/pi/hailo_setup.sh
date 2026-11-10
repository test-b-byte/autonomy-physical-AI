#!/usr/bin/env bash
# Raspberry Pi 5 + Hailo AI HAT bring-up.  Three steps, each ends in a reboot
# except verify:
#
#   bash pi/hailo_setup.sh firmware   # OS + bootloader up to date, PCIe Gen 3
#   bash pi/hailo_setup.sh install    # Hailo driver, runtime, models (hailo-all)
#   bash pi/hailo_setup.sh verify     # device visible, runtime imports, not throttled
set -euo pipefail
CONFIG=/boot/firmware/config.txt

case "${1:-}" in
  firmware)
    sudo apt update && sudo apt full-upgrade -y
    sudo rpi-eeprom-update -a
    grep -q '^dtparam=pciex1_gen=3' "$CONFIG" || echo 'dtparam=pciex1_gen=3' | sudo tee -a "$CONFIG"
    echo "rebooting — then run: bash $0 install"; sleep 3; sudo reboot ;;
  install)
    sudo apt install -y dkms hailo-all
    echo "rebooting — then run: bash $0 verify"; sleep 3; sudo reboot ;;
  verify)
    lspci | grep -i hailo || echo "WARNING: no Hailo device on PCIe — reseat the HAT ribbon"
    hailortcli fw-control identify
    python3 -c "import hailo_platform; print('hailo_platform OK')"
    ls /usr/share/hailo-models/*.hef 2>/dev/null | head -5 || echo "no system .hef models"
    vcgencmd get_throttled            # want throttled=0x0 — otherwise use the 27 W PSU
    ;;
  *) echo "usage: $0 {firmware|install|verify}"; exit 1 ;;
esac
