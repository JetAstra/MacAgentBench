#!/bin/bash
set -e

# Use qcow2 overlay instead of full copy (takes < 1 second)
qemu-img create -f qcow2 -b /home/arch/OSX-KVM/mac_hdd_ng_src.img -F qcow2 /home/arch/OSX-KVM/mac_hdd_ng.img
cp /home/arch/OSX-KVM/BaseSystem_src.img /home/arch/OSX-KVM/BaseSystem.img

# === 1. Check if BaseSystem.img is missing, download or create it ===
if [[ ! -e "${BASESYSTEM_IMAGE:-BaseSystem.img}" ]]; then
    echo "No BaseSystem.img available, downloading ${SHORTNAME}"
    make
    qemu-img convert BaseSystem.dmg -O qcow2 -p -c "${BASESYSTEM_IMAGE:-BaseSystem.img}"
    rm -f ./BaseSystem.dmg
fi

# === 2. Touch device files and ensure correct ownership ===
sudo touch /dev/kvm /dev/snd "${IMAGE_PATH}" "${BOOTDISK}" "${ENV}" 2>/dev/null || true
sudo chown -R "$(id -u)":"$(id -g)" /dev/kvm /dev/snd "${IMAGE_PATH}" "${BOOTDISK}" "${ENV}" 2>/dev/null || true

# === 3. Handle NOPICKER bootdisk option ===
if [[ "${NOPICKER}" == true ]]; then
    sed -i '/^.*InstallMedia.*/d' Launch.sh
    export BOOTDISK="${BOOTDISK:=/home/arch/OSX-KVM/OpenCore/OpenCore-nopicker.qcow2}"
else
    export BOOTDISK="${BOOTDISK:=/home/arch/OSX-KVM/OpenCore/OpenCore.qcow2}"
fi

# === 4. Generate Unique Serial Bootdisk if required ===
if [[ "${GENERATE_UNIQUE}" == true ]]; then
    ./Docker-OSX/osx-serial-generator/generate-unique-machine-values.sh \
        --count 1 \
        --tsv ./serial.tsv \
        --bootdisks \
        --width "${WIDTH:-1920}" \
        --height "${HEIGHT:-1080}" \
        --output-bootdisk "${BOOTDISK}" \
        --output-env "${ENV:=/env}" || exit 1
fi

# === 5. Generate Specific Serial Bootdisk if required ===
if [[ "${GENERATE_SPECIFIC}" == true ]]; then
    source "${ENV:=/env}" 2>/dev/null
    ./Docker-OSX/osx-serial-generator/generate-specific-bootdisk.sh \
        --model "${DEVICE_MODEL}" \
        --serial "${SERIAL}" \
        --board-serial "${BOARD_SERIAL}" \
        --uuid "${UUID}" \
        --mac-address "${MAC_ADDRESS}" \
        --width "${WIDTH:-1920}" \
        --height "${HEIGHT:-1080}" \
        --output-bootdisk "${BOOTDISK}" || exit 1
fi

# === 6. Enable SSH and launch system ===
./enable-ssh.sh
exec /bin/bash -c ./Launch.sh
