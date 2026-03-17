#!/bin/bash

sudo docker run -itd \
    --name "macos_arena2" \
    --device /dev/kvm \
    -p 52271:10022 \
    -p 5901:5901 \
    --add-host=host.docker.internal:host-gateway \
    -e "DISPLAY=${DISPLAY:-:0.0}" \
    -e EXTRA="-vnc 0.0.0.0:1,password=off" \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e CPU='Haswell-noTSX' \
    -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
    -v "/home/fuyikun/Documents/ckpt/all4/mac_hdd_ng.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
    -v "/home/fuyikun/Documents/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
    -e SHORTNAME=sonoma \
    -e USERNAME=pipiwu \
    -e PASSWORD='1234' \
    numbmelon/docker-osx-evalkit-auto:latest
# Note:
# Some tasks require internet connectivity inside the Docker container.
# Make sure the container has proper network access. If necessary, you can
# inject proxy settings using `-e` options during container startup.
# For example:
#   -e http_proxy="http://<proxy_host>:<proxy_port>" \
#   -e https_proxy="http://<proxy_host>:<proxy_port>" \
#   -e HTTP_PROXY="http://<proxy_host>:<proxy_port>" \
#   -e HTTPS_PROXY="http://<proxy_host>:<proxy_port>" \